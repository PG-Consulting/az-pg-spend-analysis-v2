/**
 * @fileoverview Tests for the ProcessingOverlay component.
 *
 * (g) Quando o job falha, o overlay deve mostrar o erro REAL em estilo
 * destrutivo (vermelho) em vez do texto genérico
 * "Aguarde enquanto a IA processa o arquivo.".
 */

import React from 'react'
import { render, screen } from '@testing-library/react'
import { ProcessingOverlay } from '../components/ProcessingOverlay'

const GENERIC_SUB = 'Aguarde enquanto a IA processa o arquivo.'
const ERROR_MSG =
  'Créditos da API xAI esgotados ou chave inválida (HTTP 403). ' +
  'Recarregue créditos no console.x.ai e re-submeta o job.'

describe('ProcessingOverlay', () => {
  it('shows the real error in red instead of the generic subMessage', () => {
    render(
      <ProcessingOverlay
        isVisible
        message="Classificando itens..."
        subMessage={GENERIC_SUB}
        error={ERROR_MSG}
        onCancel={() => {}}
      />
    )

    const errorEl = screen.getByText(ERROR_MSG)
    expect(errorEl).toBeInTheDocument()
    expect(errorEl.className).toContain('text-red')
    expect(screen.queryByText(GENERIC_SUB)).not.toBeInTheDocument()
  })

  it('switches the action button to "Fechar" when an error is present', () => {
    render(
      <ProcessingOverlay
        isVisible
        message="Classificando itens..."
        subMessage={GENERIC_SUB}
        error={ERROR_MSG}
        onCancel={() => {}}
      />
    )

    expect(screen.getByRole('button', { name: 'Fechar' })).toBeInTheDocument()
    expect(screen.queryByText('Cancelar classificação')).not.toBeInTheDocument()
  })

  it('keeps the generic subMessage and cancel button when there is no error', () => {
    render(
      <ProcessingOverlay
        isVisible
        message="Classificando itens..."
        subMessage={GENERIC_SUB}
        progress={42}
        onCancel={() => {}}
      />
    )

    expect(screen.getByText(GENERIC_SUB)).toBeInTheDocument()
    expect(screen.getByText('Cancelar classificação')).toBeInTheDocument()
    expect(screen.getByText('42%')).toBeInTheDocument()
  })
})
