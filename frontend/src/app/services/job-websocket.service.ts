// frontend/src/app/services/job-websocket.service.ts
import { inject, Injectable, OnDestroy, signal } from '@angular/core';
import { Router } from '@angular/router';
import { WebSocketEvent, WebSocketStage } from '../models/job.model';
import { StorageService } from './storage.service';

export interface WebSocketState {
  stage: WebSocketStage | null;
  // extracting
  totalFrames: number;
  // deduplicating
  keptFrames: number;
  dedupTotal: number;
  // transcribing
  chunksProcessed: number;
  totalChunks: number;
  // analysing
  analysedFrames: number;
  analysingTotal: number;
  // error
  errorMessage: string | null;
  // terminal
  downloadReady: boolean;
}

const INITIAL_STATE: WebSocketState = {
  stage: null,
  totalFrames: 0,
  keptFrames: 0,
  dedupTotal: 0,
  chunksProcessed: 0,
  totalChunks: 0,
  analysedFrames: 0,
  analysingTotal: 0,
  errorMessage: null,
  downloadReady: false,
};

const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_BASE_DELAY_MS = 2000;

@Injectable({ providedIn: 'root' })
export class JobWebSocketService implements OnDestroy {
  private storageService = inject(StorageService);
  private router = inject(Router);

  // Public reactive state — components read these signals
  wsState = signal<WebSocketState>({ ...INITIAL_STATE });
  isConnected = signal(false);

  private socket: WebSocket | null = null;
  private jobId: string | null = null;
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private intentionalClose = false;

  connect(jobId: string, wsUrl: string): void {
    // Disconnect any existing socket cleanly before opening a new one
    if (this.socket) {
      this.disconnect();
    }

    this.jobId = jobId;
    this.intentionalClose = false;
    this.reconnectAttempts = 0;
    this.wsState.set({ ...INITIAL_STATE });

    this.openSocket(wsUrl);
  }

  disconnect(): void {
    this.intentionalClose = true;
    this.clearReconnectTimer();

    if (this.socket) {
      this.socket.close(1000, 'Client disconnected');
      this.socket = null;
    }

    this.isConnected.set(false);
    this.jobId = null;
  }

  private openSocket(wsUrl: string): void {
    console.log(`[WS] Connecting to ${wsUrl}`);

    try {
      this.socket = new WebSocket(wsUrl);
    } catch (err) {
      console.error('[WS] Failed to construct WebSocket:', err);
      this.handleReconnect(wsUrl);
      return;
    }

    this.socket.onopen = () => {
      console.log('[WS] Connected');
      this.isConnected.set(true);
      this.reconnectAttempts = 0;
    };

    this.socket.onmessage = (event: MessageEvent) => {
      this.handleMessage(event);
    };

    this.socket.onerror = (event) => {
      console.error('[WS] Socket error:', event);
      // onclose always fires after onerror — reconnect logic lives there
    };

    this.socket.onclose = (event: CloseEvent) => {
      console.log(`[WS] Closed — code ${event.code}, intentional: ${this.intentionalClose}`);
      this.isConnected.set(false);
      this.socket = null;

      const isTerminalStage =
        this.wsState().stage === 'complete' ||
        this.wsState().stage === 'error';

      if (!this.intentionalClose && !isTerminalStage) {
        this.handleReconnect(wsUrl);
      }
    };
  }

  private handleMessage(event: MessageEvent): void {
    let parsed: WebSocketEvent;

    try {
      parsed = JSON.parse(event.data as string) as WebSocketEvent;
    } catch {
      console.warn('[WS] Could not parse message:', event.data);
      return;
    }

    // Merge incoming event into state
    const current = this.wsState();

    switch (parsed.stage) {
      case 'extracting':
        this.wsState.set({
          ...current,
          stage: 'extracting',
          totalFrames: parsed.totalFrames,
        });
        break;

      case 'deduplicating':
        this.wsState.set({
          ...current,
          stage: 'deduplicating',
          keptFrames: parsed.kept,
          dedupTotal: parsed.total,
        });
        break;

      case 'transcribing':
        this.wsState.set({
          ...current,
          stage: 'transcribing',
          chunksProcessed: parsed.chunksProcessed,
          totalChunks: parsed.totalChunks,
        });
        break;

      case 'analysing':
        this.wsState.set({
          ...current,
          stage: 'analysing',
          analysedFrames: parsed.framed,
          analysingTotal: parsed.totalFrames,
        });
        break;

      case 'assembling':
        this.wsState.set({ ...current, stage: 'assembling' });
        break;

      case 'complete':
        this.wsState.set({
          ...current,
          stage: 'complete',
          downloadReady: true,
        });
        // Navigate to download page — jobId is guaranteed set while socket is open
        if (this.jobId) {
          this.router.navigate(['/download', this.jobId]);
        }
        this.disconnect();
        break;

      case 'error':
        this.wsState.set({
          ...current,
          stage: 'error',
          errorMessage: parsed.message,
        });
        this.storageService.clearPendingJob();
        this.disconnect();
        break;
    }
  }

  private handleReconnect(wsUrl: string): void {
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      console.error('[WS] Max reconnect attempts reached');
      this.wsState.update(s => ({
        ...s,
        stage: 'error',
        errorMessage: 'Connection lost. Please refresh the page.',
      }));
      this.storageService.clearPendingJob();
      return;
    }

    // Exponential backoff: 2s, 4s, 8s, 16s, 32s
    const delay = RECONNECT_BASE_DELAY_MS * Math.pow(2, this.reconnectAttempts);
    this.reconnectAttempts++;

    console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    this.reconnectTimer = setTimeout(() => {
      this.openSocket(wsUrl);
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  ngOnDestroy(): void {
    this.disconnect();
  }
}