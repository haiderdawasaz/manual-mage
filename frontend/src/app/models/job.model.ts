// frontend/src/app/models/job.model.ts
import { Timestamp } from '@angular/fire/firestore';

export type JobStatus = 'pending' | 'processing' | 'complete' | 'expired' | 'error' | 'cancelled';

export type WebSocketStage =
  | 'extracting'
  | 'deduplicating'
  | 'transcribing'
  | 'analysing'
  | 'assembling'
  | 'complete'
  | 'error';

export interface JobProgress {
  stage: string;
  totalFrames: number;
  deduplicatedFrames: number;
  analysedFrames: number;
  totalAudioChunks: number;
  transcribedChunks: number;
}

export interface ProcessingJob {
  id: string;
  userId: string;
  videoFileName: string;
  createdAt: Timestamp;
  updatedAt: Timestamp;
  status: JobStatus;
  progress: JobProgress;
  hasAudio: boolean;
  completedAt?: Timestamp;
  expiresAt?: Timestamp;
  downloadToken?: string;
  error?: string;
}

// WebSocket event shapes — server → client only
export interface WsExtractingEvent {
  stage: 'extracting';
  totalFrames: number;
}

export interface WsDeduplicatingEvent {
  stage: 'deduplicating';
  kept: number;
  total: number;
}

export interface WsTranscribingEvent {
  stage: 'transcribing';
  chunksProcessed: number;
  totalChunks: number;
}

export interface WsAnalysingEvent {
  stage: 'analysing';
  framed: number;
  totalFrames: number;
}

export interface WsAssemblingEvent {
  stage: 'assembling';
}

export interface WsCompleteEvent {
  stage: 'complete';
  downloadReady: true;
}

export interface WsErrorEvent {
  stage: 'error';
  message: string;
}

export type WebSocketEvent =
  | WsExtractingEvent
  | WsDeduplicatingEvent
  | WsTranscribingEvent
  | WsAnalysingEvent
  | WsAssemblingEvent
  | WsCompleteEvent
  | WsErrorEvent;

// What Angular persists to localStorage
export interface PendingJob {
  jobId: string;
  videoFileName: string;
  startedAt: number; // Date.now() timestamp
}