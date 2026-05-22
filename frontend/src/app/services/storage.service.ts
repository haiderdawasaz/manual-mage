// frontend/src/app/services/storage.service.ts
import { Injectable } from '@angular/core';
import { PendingJob } from '../models/job.model';

const PENDING_JOB_KEY = 'vtd_pending_job';

@Injectable({ providedIn: 'root' })
export class StorageService {

  savePendingJob(job: PendingJob): void {
    try {
      localStorage.setItem(PENDING_JOB_KEY, JSON.stringify(job));
    } catch {
      // Storage quota exceeded or private browsing — fail silently
      console.warn('[StorageService] Could not save pending job to localStorage');
    }
  }

  getPendingJob(): PendingJob | null {
    try {
      const raw = localStorage.getItem(PENDING_JOB_KEY);
      if (!raw) return null;
      return JSON.parse(raw) as PendingJob;
    } catch {
      this.clearPendingJob();
      return null;
    }
  }

  clearPendingJob(): void {
    try {
      localStorage.removeItem(PENDING_JOB_KEY);
    } catch {
      // Ignore
    }
  }

  hasPendingJob(): boolean {
    return this.getPendingJob() !== null;
  }
}