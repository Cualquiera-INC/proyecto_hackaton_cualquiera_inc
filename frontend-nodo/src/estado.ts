/** Colores semánticos compatibles con el fondo navy del logo. */
export function estadoTone(estado: string): 'ruta' | 'entregado' | 'pendiente' | 'prep' | 'otro' {
  const e = estado.toLowerCase()
  if (e.includes('ruta')) return 'ruta'
  if (e.includes('entregado')) return 'entregado'
  if (e.includes('pendiente')) return 'pendiente'
  if (e.includes('preparación') || e.includes('preparacion')) return 'prep'
  return 'otro'
}
