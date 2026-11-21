export type Pedido = {
  id: string
  zona: string
  estado: string
}

export type PedidosResponse = {
  instancia: string
  version: string
  pedidos: Pedido[]
}

export type HealthResponse = {
  estado: string
  instancia: string
  version_datos?: string
}

export type HealthState =
  | { status: 'loading' }
  | { status: 'ok'; data: HealthResponse }
  | { status: 'error'; message: string; http?: number }
