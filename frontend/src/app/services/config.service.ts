// services/config.service.ts
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class ConfigService {
  private config: any;

  constructor(private http: HttpClient) {}

  async loadConfig() {
    // This hits the Nginx endpoint we set up earlier
    this.config = await firstValueFrom(this.http.get('/api/config'));
  }

  get firebaseConfig() {
    return this.config?.firebaseConfig;
  }

  get backendUrl() {
    return this.config?.backendUrl;
  }
}