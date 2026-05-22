// frontend/src/app/services/auth.service.ts
import { inject, Injectable, signal } from '@angular/core';
import {
  Auth,
  GoogleAuthProvider,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  user,
  getIdToken,
} from '@angular/fire/auth';
import { toSignal } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { map } from 'rxjs';
import { AppUser } from '../models/user.model';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private auth = inject(Auth);
  private router = inject(Router);

  // Reactive signal — components read this, never call getAuth() themselves
  currentUser = toSignal(
    user(this.auth).pipe(
      map(u =>
        u
          ? ({
              uid: u.uid,
              email: u.email,
              displayName: u.displayName,
              photoURL: u.photoURL,
            } satisfies AppUser)
          : null,
      ),
    ),
  );

  isAuthenticated = toSignal(
    user(this.auth).pipe(map(u => !!u)),
    { initialValue: false },
  );

  // Error signal — auth component reads this to display messages
  authError = signal<string | null>(null);
  isLoading = signal(false);

  async signInWithEmail(email: string, password: string): Promise<void> {
    this.authError.set(null);
    this.isLoading.set(true);
    try {
      await signInWithEmailAndPassword(this.auth, email, password);
      await this.router.navigate(['/upload']);
    } catch (err) {
      this.authError.set(this.friendlyError(err));
    } finally {
      this.isLoading.set(false);
    }
  }

  async registerWithEmail(email: string, password: string): Promise<void> {
    this.authError.set(null);
    this.isLoading.set(true);
    try {
      await createUserWithEmailAndPassword(this.auth, email, password);
      await this.router.navigate(['/upload']);
    } catch (err) {
      this.authError.set(this.friendlyError(err));
    } finally {
      this.isLoading.set(false);
    }
  }

  async signInWithGoogle(): Promise<void> {
    this.authError.set(null);
    this.isLoading.set(true);
    try {
      const provider = new GoogleAuthProvider();
      await signInWithPopup(this.auth, provider);
      await this.router.navigate(['/upload']);
    } catch (err) {
      this.authError.set(this.friendlyError(err));
    } finally {
      this.isLoading.set(false);
    }
  }

  async signOut(): Promise<void> {
    await signOut(this.auth);
    await this.router.navigate(['/auth']);
  }

  // Returns a fresh Firebase ID token for backend Authorization headers
  async getIdToken(): Promise<string | null> {
    const currentUser = this.auth.currentUser;
    if (!currentUser) return null;
    return getIdToken(currentUser);
  }

  private friendlyError(err: unknown): string {
    if (err instanceof Error) {
      const code = (err as { code?: string }).code ?? '';
      const messages: Record<string, string> = {
        'auth/user-not-found': 'No account found with this email.',
        'auth/wrong-password': 'Incorrect password.',
        'auth/email-already-in-use': 'An account with this email already exists.',
        'auth/weak-password': 'Password must be at least 6 characters.',
        'auth/invalid-email': 'Please enter a valid email address.',
        'auth/popup-closed-by-user': 'Google sign-in was cancelled.',
        'auth/too-many-requests': 'Too many attempts. Please try again later.',
        'auth/invalid-credential': 'Invalid email or password.',
      };
      return messages[code] ?? err.message;
    }
    return 'An unexpected error occurred.';
  }
}