// frontend/src/app/components/upload/upload.component.ts
import { Component, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { JobService } from '../../services/job.service';
import { StorageService } from '../../services/storage.service';

type UploadState = 'idle' | 'uploading' | 'error';

const ACCEPTED_TYPES = ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/webm'];
const MAX_DURATION_SECONDS = 300;
const MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024 * 1024; // 2 GB

@Component({
  selector: 'app-upload',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './upload.component.html',
})
export class UploadComponent implements OnInit {
  private jobService = inject(JobService);
  private storageService = inject(StorageService);
  private router = inject(Router);

  readonly infoItems = [
    { label: 'Formats', value: 'MP4 · MOV · AVI · WebM' },
    { label: 'Max Length', value: '5 Minutes' },
    { label: 'Output', value: 'Editable DOCX' },
  ];

  uploadState = signal<UploadState>('idle');
  errorMessage = signal<string | null>(null);
  isDragOver = signal(false);
  selectedFile = signal<File | null>(null);
  uploadProgress = signal(0);
  pendingJob = signal<{ jobId: string; videoFileName: string } | null>(null);
  isDismissing = signal(false);

  ngOnInit(): void {
    const pending = this.storageService.getPendingJob();
    if (pending) {
      this.pendingJob.set({
        jobId: pending.jobId,
        videoFileName: pending.videoFileName,
      });
    }
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver.set(true);
  }

  onDragLeave(): void {
    this.isDragOver.set(false);
  }

  async onDrop(event: DragEvent): Promise<void> {
    event.preventDefault();
    this.isDragOver.set(false);
    const file = event.dataTransfer?.files[0];
    if (file) await this.selectFile(file);
  }

  async onFileInput(event: Event): Promise<void> {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (file) await this.selectFile(file);
  }

  private async selectFile(file: File): Promise<void> {
    this.errorMessage.set(null);
    if (!ACCEPTED_TYPES.includes(file.type)) {
      this.errorMessage.set('Unsupported format. Please upload an MP4, MOV, AVI, or WebM file.');
      return;
    }

    try {
      const duration = await this.getVideoDuration(file);
      if (duration > MAX_DURATION_SECONDS) {
        this.errorMessage.set('Video too long. Maximum length is 5 minutes.');
        return;
      }
    } catch (err) {
      this.errorMessage.set('Could not read video metadata. Please try a different file.');
      return;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
      this.errorMessage.set(`File too large. Maximum size is 2 GB.`);
      return;
    }
    this.selectedFile.set(file);
  }

  private getVideoDuration(file: File): Promise<number> {
    return new Promise((resolve, reject) => {
      const video = document.createElement('video');
      video.preload = 'metadata';
      video.onloadedmetadata = () => {
        window.URL.revokeObjectURL(video.src);
        resolve(video.duration);
      };
      video.onerror = () => {
        window.URL.revokeObjectURL(video.src);
        reject('Error loading video metadata');
      };
      video.src = URL.createObjectURL(file);
    });
  }

  clearFile(): void {
    this.selectedFile.set(null);
    this.errorMessage.set(null);
  }

  async startUpload(): Promise<void> {
    const file = this.selectedFile();
    if (!file || this.uploadState() === 'uploading') return;

    this.uploadState.set('uploading');
    this.errorMessage.set(null);
    this.uploadProgress.set(0);

    try {
      const progressInterval = setInterval(() => {
        if (this.uploadProgress() < 85) {
          this.uploadProgress.update(p => p + 5);
        }
      }, 300);

      const response = await this.jobService.startJob(file);

      clearInterval(progressInterval);
      this.uploadProgress.set(100);

      await this.router.navigate(['/progress', response.job_id]);

    } catch (err) {
      this.uploadState.set('error');
      this.errorMessage.set(
        err instanceof Error ? err.message : 'Upload failed. Please try again.',
      );
      this.storageService.clearPendingJob();
    }
  }

  async resumePendingJob(): Promise<void> {
    const pending = this.pendingJob();
    if (!pending) return;

    const job = await this.jobService.getJobFromFirestore(pending.jobId);

    if (!job) {
      this.storageService.clearPendingJob();
      this.pendingJob.set(null);
      return;
    }

    switch (job.status) {
      case 'processing':
        await this.router.navigate(['/progress', pending.jobId]);
        break;
      case 'complete':
        await this.router.navigate(['/download', pending.jobId]);
        break;
      case 'expired':
      case 'error':
        this.storageService.clearPendingJob();
        this.pendingJob.set(null);
        this.errorMessage.set(
          job.status === 'expired'
            ? 'Your previous session expired. Please upload your video again.'
            : 'Your previous job encountered an error. Please try again.',
        );
        break;
    }
  }

  async dismissPendingJob(): Promise<void> {
    if (this.isDismissing()) return;
    const pending = this.pendingJob();
    if (!pending) return;

    this.isDismissing.set(true);
    await this.jobService.cancelJob(pending.jobId);
    this.storageService.clearPendingJob();
    this.pendingJob.set(null);
    this.isDismissing.set(false);
  }

  formatFileSize(bytes: number): string {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  }

  get acceptedExtensions(): string {
    return '.mp4,.mov,.avi,.webm';
  }
}