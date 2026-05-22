// frontend/src/app/app.config.ts
import { APP_INITIALIZER, ApplicationConfig, provideZoneChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withFetch } from '@angular/common/http';
import { initializeApp, provideFirebaseApp } from '@angular/fire/app';
import { getAuth, provideAuth } from '@angular/fire/auth';
import { getFirestore, provideFirestore } from '@angular/fire/firestore';
import { routes } from './app.routes';
// import { environment } from '../environments/environment';
import { ConfigService } from './services/config.service';

// export function initializeAppCustom(configService: ConfigService) {
//   return async () => {
//     await configService.loadConfig();
//     // Initialize Firebase once the config is fetched
//     initializeApp(configService.firebaseConfig);
//   };
// }

// export const appConfig: ApplicationConfig = {
//   providers: [
//     provideZoneChangeDetection({ eventCoalescing: true }),
//     provideRouter(routes),
//     provideHttpClient(withFetch()),
//     provideFirebaseApp(() => initializeApp(environment.firebase)),
//     provideAuth(() => getAuth()),
//     provideFirestore(() => getFirestore()),
//   ],
// };

// Factory function to load config before the app starts
export function initializeAppFactory(configService: ConfigService) {
  return () => configService.loadConfig();
}

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes),
    provideHttpClient(withFetch()),

    // 1. Load the configuration from Nginx first
    {
      provide: APP_INITIALIZER,
      useFactory: initializeAppFactory,
      deps: [ConfigService],
      multi: true,
    },

    // 2. Initialize Firebase using the data fetched by ConfigService
    // Angular Fire's provideFirebaseApp accepts a factory that can access the Service
    provideFirebaseApp((injector) => {
      const configService = injector.get(ConfigService);
      return initializeApp(configService.firebaseConfig);
    }),

    provideAuth(() => getAuth()),
    provideFirestore(() => getFirestore()),
  ],
};