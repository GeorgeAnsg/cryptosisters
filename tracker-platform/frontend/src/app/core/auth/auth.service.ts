import { Injectable, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { HttpClient } from '@angular/common/http';
import {
  Auth,
  authState,
  createUserWithEmailAndPassword,
  GoogleAuthProvider,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
} from '@angular/fire/auth';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly auth = inject(Auth);
  private readonly http = inject(HttpClient);

  // null = no logueado, undefined = todavia resolviendo el estado inicial
  readonly usuario = toSignal(authState(this.auth), { initialValue: undefined });

  // Firebase emite un objeto User NUEVO en cada refresco de token (misma
  // sesion, misma persona) -- un effect() que dependa de "usuario" entero
  // se repite en cada refresco porque la comparacion es por referencia, lo
  // que disparaba un refetch en cadena de /candidatos y /usuarios/sigue
  // (a veces coincidiendo con que el token nuevo aun no estaba listo, 401).
  // Los effects deben depender de esto, no de "usuario" directamente.
  readonly uid = computed(() => this.usuario()?.uid ?? null);

  async login(email: string, password: string) {
    await signInWithEmailAndPassword(this.auth, email, password);
    await this.abrirSesion();
  }

  async registrar(email: string, password: string) {
    await createUserWithEmailAndPassword(this.auth, email, password);
    await this.abrirSesion();
  }

  async loginConGoogle() {
    await signInWithPopup(this.auth, new GoogleAuthProvider());
    await this.abrirSesion();
  }

  logout() {
    return signOut(this.auth);
  }

  // crea la fila en la tabla "usuarios" del backend la primera vez que este
  // uid inicia sesion -- idempotente (INSERT OR IGNORE), asi que llamarlo en
  // cada login no duplica nada
  private abrirSesion() {
    return firstValueFrom(this.http.post(`${environment.apiUrl}/usuarios/sesion`, {}));
  }
}
