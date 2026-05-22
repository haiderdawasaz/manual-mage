// frontend/src/app/app.routes.ts
import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    redirectTo: 'upload',
    pathMatch: 'full',
  },
  {
    path: 'upload',
    loadComponent: () =>
      import('./components/upload/upload.component').then(m => m.UploadComponent),
  },
  {
    path: 'progress/:jobId',
    loadComponent: () =>
      import('./components/progress/progress.component').then(m => m.ProgressComponent),
  },
  {
    path: 'download/:jobId',
    loadComponent: () =>
      import('./components/download/download.component').then(m => m.DownloadComponent),
  },
  {
    path: '**',
    redirectTo: 'upload',
  },
];