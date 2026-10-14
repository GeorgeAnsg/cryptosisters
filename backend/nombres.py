"""Asigna el mismo nombre de planta que usa el frontend (static/index.html,
PLANTAS/hashAddr/asignarPlantas) para que las alertas de Telegram usen el
mismo nombre que se ve en la web, en vez de la dirección en crudo."""

PLANTAS = ['Roble', 'Sauce', 'Bambú', 'Olivo', 'Ciprés', 'Abedul', 'Acacia', 'Laurel', 'Jazmín', 'Lavanda',
           'Romero', 'Tomillo', 'Helecho', 'Magnolia', 'Cerezo', 'Pino', 'Cedro', 'Haya', 'Álamo', 'Arce',
           'Eucalipto', 'Hiedra', 'Loto', 'Girasol', 'Orquídea', 'Bonsái', 'Palmera', 'Secuoya', 'Baobab', 'Mimosa',
           'Nogal', 'Fresno', 'Tilo', 'Azalea', 'Camelia', 'Begonia', 'Hortensia', 'Tulipán', 'Narciso', 'Peonía']


def _hash_addr(addr):
    h = 0
    for ch in addr:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
        if h >= 0x80000000:
            h -= 0x100000000
    return abs(h)


def nombre_de(addr, todas_direcciones):
    """todas_direcciones: direcciones de TODOS los candidatos actuales (el
    mismo conjunto que ve el frontend), para que el reparto evite las mismas
    colisiones y de el mismo resultado."""
    usadas = set()
    asignado = {}
    for a in sorted(set(todas_direcciones) | {addr}):
        i = _hash_addr(a) % len(PLANTAS)
        intentos = 0
        while PLANTAS[i] in usadas and intentos < len(PLANTAS):
            i = (i + 1) % len(PLANTAS)
            intentos += 1
        asignado[a] = PLANTAS[i]
        usadas.add(PLANTAS[i])
    return asignado.get(addr, addr[:6])
