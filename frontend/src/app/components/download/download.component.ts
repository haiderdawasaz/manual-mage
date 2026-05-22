import {
  Component,
  inject,
  OnDestroy,
  OnInit,
  computed,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { Firestore, doc, onSnapshot } from '@angular/fire/firestore';
import { JobService } from '../../services/job.service';
import { StorageService } from '../../services/storage.service';
import { ProcessingJob } from '../../models/job.model';

type DownloadPageState = 'loading' | 'ready' | 'expired' | 'error';

@Component({
  selector: 'app-download',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './download.component.html',
})
export class DownloadComponent implements OnInit, OnDestroy {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private firestore = inject(Firestore);
  private jobService = inject(JobService);
  private storageService = inject(StorageService);

  // ── State signals ─────────────────────────────────────────────────────────
  pageState = signal<DownloadPageState>('loading');
  job = signal<ProcessingJob | null>(null);
  secondsRemaining = signal(0);
  isDownloading = signal(false);
  downloadError = signal<string | null>(null);
  jobId = signal<string | null>(null);

  // ── Computed ──────────────────────────────────────────────────────────────
  minutesRemaining = computed(() => {
    const s = this.secondsRemaining();
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${sec.toString().padStart(2, '0')}`;
  });

  expiryUrgent = computed(() => this.secondsRemaining() <= 60);

  videoFileName = computed(() => {
    const name = this.job()?.videoFileName ?? 'document';
    return name.replace(/\.[^/.]+$/, '');
  });

  // ── Private handles ───────────────────────────────────────────────────────
  private countdownTimer: ReturnType<typeof setInterval> | null = null;
  private firestoreUnsub: (() => void) | null = null;

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('jobId');
    if (!id) {
      this.pageState.set('error');
      return;
    }
    this.jobId.set(id);
    this.subscribeToJob(id);
  }

  ngOnDestroy(): void {
    this.clearCountdown();
    if (this.firestoreUnsub) {
      this.firestoreUnsub();
    }
  }

  // ── Firestore real-time listener ──────────────────────────────────────────
  private subscribeToJob(jobId: string): void {
    const ref = doc(this.firestore, 'jobs', jobId);

    this.firestoreUnsub = onSnapshot(
      ref,
      snap => {
        if (!snap.exists()) {
          this.pageState.set('error');
          this.storageService.clearPendingJob();
          return;
        }

        const data = { id: snap.id, ...snap.data() } as ProcessingJob;
        this.job.set(data);

        switch (data.status) {
          case 'complete':
            this.pageState.set('ready');
            this.startCountdown(data);
            break;
          case 'expired':
            this.pageState.set('expired');
            this.clearCountdown();
            this.storageService.clearPendingJob();
            break;
          case 'processing':
            this.router.navigate(['/progress', jobId]);
            break;
          case 'error':
            this.pageState.set('error');
            this.storageService.clearPendingJob();
            break;
        }
      },
      err => {
        console.error('[DownloadComponent] Firestore error:', err);
        this.pageState.set('error');
      },
    );
  }

  // ── Countdown timer ───────────────────────────────────────────────────────
  private startCountdown(job: ProcessingJob): void {
    if (this.countdownTimer !== null) return;

    const expiresAt = job.expiresAt?.toMillis() ?? 0;

    const tick = (): void => {
      const remaining = Math.max(0, Math.floor((expiresAt - Date.now()) / 1000));
      this.secondsRemaining.set(remaining);
      if (remaining === 0) {
        this.clearCountdown();
        this.pageState.set('expired');
        this.storageService.clearPendingJob();
      }
    };

    tick();
    this.countdownTimer = setInterval(tick, 1000);
  }

  private clearCountdown(): void {
    if (this.countdownTimer !== null) {
      clearInterval(this.countdownTimer);
      this.countdownTimer = null;
    }
  }

  // ── Download ──────────────────────────────────────────────────────────────
  async triggerDownload(): Promise<void> {
    const currentJob = this.job();
    const id = this.jobId();

    if (!currentJob?.downloadToken || !id || this.isDownloading()) return;

    this.isDownloading.set(true);
    this.downloadError.set(null);

    try {
      const url = this.jobService.buildDownloadUrl(id, currentJob.downloadToken);
      const response = await fetch(url);

      if (!response.ok) {
        if (response.status === 410) {
          this.pageState.set('expired');
          this.storageService.clearPendingJob();
          return;
        }
        throw new Error(`Download failed (${response.status})`);
      }

      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = `${this.videoFileName()}_manual.docx`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(objectUrl);

    } catch (err) {
      this.downloadError.set(
        err instanceof Error ? err.message : 'Download failed. Please try again.',
      );
    } finally {
      this.isDownloading.set(false);
    }
  }

  startOver(): void {
    this.storageService.clearPendingJob();
    this.router.navigate(['/upload']);
  }
}