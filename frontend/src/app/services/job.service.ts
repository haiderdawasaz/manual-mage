// frontend/src/app/services/job.service.ts
import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Firestore, doc, getDoc, docData } from '@angular/fire/firestore';
import { firstValueFrom, Observable } from 'rxjs';
import { StorageService } from './storage.service';
import { ProcessingJob } from '../models/job.model';
// import { environment } from '../../environments/environment';
import { ConfigService } from './config.service';

export interface StartJobResponse {
  job_id: string;
}

@Injectable({ providedIn: 'root' })
export class JobService {
  private http = inject(HttpClient);
  private storage = inject(StorageService);
  private firestore = inject(Firestore);
  private configService = inject(ConfigService);

  async startJob(file: File): Promise<StartJobResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await firstValueFrom(
      this.http.post<StartJobResponse>(
        `${this.configService.backendUrl}/jobs/start`,
        formData,
      ),
    );

    // Persist immediately so session resumption works even if browser closes
    this.storage.savePendingJob({
      jobId: response.job_id,
      videoFileName: file.name,
      startedAt: Date.now(),
    });

    return response;
  }

  getJobUpdates(jobId: string): Observable<ProcessingJob | undefined> {
    const ref = doc(this.firestore, 'jobs', jobId);
    return docData(ref) as Observable<ProcessingJob | undefined>;
  }

  async getJobFromFirestore(jobId: string): Promise<ProcessingJob | null> {
    try {
      const ref = doc(this.firestore, 'jobs', jobId);
      const snap = await getDoc(ref);
      if (!snap.exists()) return null;
      return { id: snap.id, ...snap.data() } as ProcessingJob;
    } catch (err) {
      console.error('[JobService] Firestore read failed:', err);
      return null;
    }
  }

  buildDownloadUrl(jobId: string, token: string): string {
    return `${this.configService.backendUrl}/download/${jobId}?token=${token}`;
  }

  /**
   * Terminate a job on the server: stops the pipeline, deletes all files,
   * and marks the Firestore document as cancelled.
   * Errors are swallowed — the caller should still navigate away.
   */
  async cancelJob(jobId: string): Promise<void> {
    try {
      await firstValueFrom(
        this.http.post<void>(`${this.configService.backendUrl}/jobs/${jobId}/cancel`, {}),
      );
    } catch (err) {
      console.error('[JobService] cancelJob failed:', err);
    }
  }
}