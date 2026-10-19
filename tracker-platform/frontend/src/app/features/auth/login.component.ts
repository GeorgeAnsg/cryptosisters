import { Component, signal } from '@angular/core';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { Password } from 'primeng/password';
import { Button } from 'primeng/button';
import { FirebaseError } from '@angular/fire/app';
import { AuthService } from '../../core/auth/auth.service';
import { InputTextComponent } from '../../shared/components/input-text/input-text.component';

// unica pantalla para login Y registro (alternar con "modo") -- no hay
// backend propio de usuarios, el login es Firebase Auth puro (email/
// contraseña o Google, los dos metodos que ya estan activados en el
// proyecto). Tras loguear, el backend valida el ID token de Firebase en
// cada request -- no hay sesion ni JWT propios.
@Component({
  selector: 'app-login',
  standalone: true,
  imports: [FormsModule, Password, Button, InputTextComponent],
  templateUrl: './login.component.html',
})
export class LoginComponent {
  protected readonly modo = signal<'login' | 'registro'>('login');
  protected readonly email = signal('');
  protected readonly password = signal('');
  protected readonly cargando = signal(false);
  protected readonly error = signal<string | null>(null);

  constructor(
    private readonly auth: AuthService,
    private readonly router: Router,
  ) {}

  protected alternarModo() {
    this.modo.set(this.modo() === 'login' ? 'registro' : 'login');
    this.error.set(null);
  }

  protected async enviar() {
    if (!this.email() || !this.password()) {
      this.error.set('Rellena email y contraseña.');
      return;
    }
    this.cargando.set(true);
    this.error.set(null);
    try {
      if (this.modo() === 'login') {
        await this.auth.login(this.email(), this.password());
      } else {
        await this.auth.registrar(this.email(), this.password());
      }
      this.router.navigateByUrl('/dashboard');
    } catch (e) {
      this.error.set(this.mensajeError(e));
    } finally {
      this.cargando.set(false);
    }
  }

  protected async conGoogle() {
    this.cargando.set(true);
    this.error.set(null);
    try {
      await this.auth.loginConGoogle();
      this.router.navigateByUrl('/dashboard');
    } catch (e) {
      this.error.set(this.mensajeError(e));
    } finally {
      this.cargando.set(false);
    }
  }

  private mensajeError(e: unknown): string {
    const codigo = e instanceof FirebaseError ? e.code : '';
    switch (codigo) {
      case 'auth/invalid-credential':
      case 'auth/wrong-password':
      case 'auth/user-not-found':
        return 'Email o contraseña incorrectos.';
      case 'auth/email-already-in-use':
        return 'Ya existe una cuenta con ese email.';
      case 'auth/weak-password':
        return 'La contraseña debe tener al menos 6 caracteres.';
      case 'auth/invalid-email':
        return 'Email no válido.';
      default:
        return 'Algo ha fallado. Inténtalo de nuevo.';
    }
  }
}
