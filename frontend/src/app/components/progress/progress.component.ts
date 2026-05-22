// frontend/src/app/components/progress/progress.component.ts
import { Component, inject, OnDestroy, OnInit, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { Subscription } from 'rxjs';
import { JobService } from '../../services/job.service';
import { StorageService } from '../../services/storage.service';
import { ProcessingJob } from '../../models/job.model';

interface StageDefinition {
  id: string;
  label: string;
  description: string;
}

const STAGES: StageDefinition[] = [
  {
    id: 'extracting',
    label: 'Extracting frames',
    description: 'Breaking your video into individual frames and audio chunks.',
  },
  {
    id: 'deduplicating',
    label: 'Deduplicating frames',
    description: 'Removing near-identical frames to keep only meaningful steps.',
  },
  {
    id: 'transcribing',
    label: 'Transcribing audio',
    description: 'Converting narration into time-aligned transcript segments.',
  },
  {
    id: 'analysing',
    label: 'Analysing steps',
    description: 'Generating a clear description for each unique key frame.',
  },
  {
    id: 'assembling',
    label: 'Assembling document',
    description: 'Building your editable DOCX with images and step descriptions.',
  },
  {
    id: 'complete',
    label: 'Complete',
    description: 'Your user manual is ready to download.',
  },
];

@Component({
  selector: 'app-progress',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './progress.component.html',
})
export class ProgressComponent implements OnInit, OnDestroy {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private jobService = inject(JobService);
  private storageService = inject(StorageService);

  readonly stages = STAGES;
  jobId = signal<string | null>(null);
  elapsedSeconds = signal(0);
  jobState = signal<ProcessingJob | null>(null);
  isCancelling = signal(false);

  private elapsedTimer: ReturnType<typeof setInterval> | null = null;
  private subscription: Subscription | null = null;

  // Index of the currently active stage in the STAGES array
  activeStageIndex = computed(() => {
    const job = this.jobState();
    if (!job || !job.progress) return -1;
    const stageId = job.progress.stage;
    if (!stageId || stageId === 'idle') return -1;
    return STAGES.findIndex(s => s.id === stageId);
  });

  // Human-readable status line shown beneath the spinner
  statusLine = computed(() => {
    const job = this.jobState();
    if (!job) return 'Initialising…';

    const p = job.progress;
    switch (p.stage) {
      case 'extracting':
        return p.totalFrames > 0
          ? `Found ${p.totalFrames} frames`
          : 'Scanning video…';
      case 'deduplicating':
        return p.totalFrames > 0
          ? `Kept ${p.deduplicatedFrames} of ${p.totalFrames} frames`
          : 'Comparing frames…';
      case 'transcribing':
        return p.totalAudioChunks > 0
          ? `Chunk ${p.transcribedChunks} of ${p.totalAudioChunks}`
          : 'Processing audio…';
      case 'analysing':
        return p.deduplicatedFrames > 0
          ? `Step ${p.analysedFrames} of ${p.deduplicatedFrames}`
          : 'Analysing frames…';
      case 'assembling':
        return 'Writing document…';
      case 'complete':
        return 'Done!';
      default:
        if (job.status === 'error') return job.error ?? 'An error occurred.';
        if (job.status === 'pending') return 'Waiting for backend…';
        if (job.status === 'processing' && p.stage === 'idle') return 'Starting pipeline…';
        return `Processing (${p.stage || 'idle'})…`;
    }
  });

  // Progress percentage for the progress bar (0–100)
  progressPercent = computed(() => {
    const job = this.jobState();
    if (!job) return 0;

    const p = job.progress;
    switch (p.stage) {
      case 'extracting':
        return 10;
      case 'deduplicating':
        return p.totalFrames > 0
          ? 10 + Math.round((p.deduplicatedFrames / p.totalFrames) * 20)
          : 15;
      case 'transcribing':
        return p.totalAudioChunks > 0
          ? 30 + Math.round((p.transcribedChunks / p.totalAudioChunks) * 20)
          : 35;
      case 'analysing':
        return p.deduplicatedFrames > 0
          ? 50 + Math.round((p.analysedFrames / p.deduplicatedFrames) * 40)
          : 55;
      case 'assembling':
        return 92;
      case 'complete':
        return 100;
      default:
        return 0;
    }
  });

  formatElapsed(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('jobId');
    if (!id) {
      this.router.navigate(['/upload']);
      return;
    }
    this.jobId.set(id);

    // Subscribe to Firestore updates
    this.subscription = this.jobService.getJobUpdates(id).subscribe(job => {
      if (job) {
        this.jobState.set(job);
        if (job.status === 'complete') {
          this.router.navigate(['/download', id]);
        } else if (job.status === 'cancelled') {
          // Already navigating away via cancelJob() — nothing to do here.
        }
      } else {
        // Job not found — maybe deleted or wrong ID
        this.router.navigate(['/upload']);
      }
    });

    // Initialise elapsed timer from storage if resuming same job
    const pending = this.storageService.getPendingJob();
    if (pending && pending.jobId === id) {
      const elapsedMs = Date.now() - pending.startedAt;
      this.elapsedSeconds.set(Math.max(0, Math.floor(elapsedMs / 1000)));
    }

    // Start elapsed timer
    this.elapsedTimer = setInterval(() => {
      this.elapsedSeconds.update(s => s + 1);
    }, 1000);
  }

  ngOnDestroy(): void {
    if (this.elapsedTimer) clearInterval(this.elapsedTimer);
    if (this.subscription) this.subscription.unsubscribe();
  }

  async cancelJob(): Promise<void> {
    if (this.isCancelling()) return;
    this.isCancelling.set(true);

    const id = this.jobId();
    if (id) {
      await this.jobService.cancelJob(id);
    }

    this.storageService.clearPendingJob();
    this.router.navigate(['/upload']);
  }
}