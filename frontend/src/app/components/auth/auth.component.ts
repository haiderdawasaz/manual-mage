// frontend/src/app/components/auth/auth.component.ts
import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../../services/auth.service';

type AuthMode = 'signin' | 'register';

@Component({
  selector: 'app-auth',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './auth.component.html',
})
export class AuthComponent {
  protected authService = inject(AuthService);

  mode = signal<AuthMode>('signin');
  email = signal('');
  password = signal('');

  toggleMode(): void {
    this.mode.set(this.mode() === 'signin' ? 'register' : 'signin');
    this.authService.authError.set(null);
  }

  async onSubmit(): Promise<void> {
    const e = this.email().trim();
    const p = this.password();
    if (!e || !p) return;

    if (this.mode() === 'signin') {
      await this.authService.signInWithEmail(e, p);
    } else {
      await this.authService.registerWithEmail(e, p);
    }
  }

  async onGoogle(): Promise<void> {
    await this.authService.signInWithGoogle();
  }

  onEmailChange(value: string): void { this.email.set(value); }
  onPasswordChange(value: string): void { this.password.set(value); }
}