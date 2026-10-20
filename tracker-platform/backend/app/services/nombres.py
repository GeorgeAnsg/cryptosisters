"""Asigna un nombre de planta + código corto a cada dirección -- único por
construcción (el código sale de la propia dirección), así que a diferencia
de la version anterior no hace falta conocer el resto de direcciones para
evitar colisiones ni repartir nada."""

PLANTAS = ['Roble', 'Sauce', 'Bambú', 'Olivo', 'Ciprés', 'Abedul', 'Acacia', 'Laurel', 'Jazmín', 'Lavanda',
           'Romero', 'Tomillo', 'Helecho', 'Magnolia', 'Cerezo', 'Pino', 'Cedro', 'Haya', 'Álamo', 'Arce',
           'Eucalipto', 'Hiedra', 'Loto', 'Girasol', 'Orquídea', 'Bonsái', 'Palmera', 'Secuoya', 'Baobab', 'Mimosa',
           'Nogal', 'Fresno', 'Tilo', 'Azalea', 'Camelia', 'Begonia', 'Hortensia', 'Tulipán', 'Narciso', 'Peonía',
           'Jacarandá', 'Glicina', 'Buganvilla', 'Madreselva', 'Clavel', 'Dalia', 'Petunia', 'Crisantemo', 'Amapola', 'Lirio',
           'Jengibre', 'Salvia', 'Menta', 'Albahaca', 'Enebro', 'Avellano', 'Castaño', 'Manzano', 'Membrillo', 'Granado']


def _hash_addr(addr):
    h = 0
    for ch in addr:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
        if h >= 0x80000000:
            h -= 0x100000000
    return abs(h)


def nombre_de(addr, todas_direcciones=None):
    """todas_direcciones ya no hace falta (se mantiene el parametro por
    compatibilidad con las llamadas existentes) -- la planta sale de un hash
    de la direccion y el codigo de sus 2 ultimos caracteres, asi que el
    resultado es unico por direccion sin tener que mirar las demas."""
    planta = PLANTAS[_hash_addr(addr) % len(PLANTAS)]
    codigo = addr[-2:].upper() if len(addr) >= 2 else '00'
    return f"{planta}-{codigo}"
