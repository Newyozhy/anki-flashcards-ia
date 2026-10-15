import React from 'react';
import { Sparkles, Brain, Layers, GitGraph } from 'lucide-react';

export interface LoadingSkeletonProps {
  count?: number;
  variant?: 'cards' | 'cockpit' | 'dag' | 'table';
  label?: string;
}

export const LoadingSkeleton: React.FC<LoadingSkeletonProps> = ({
  count = 3,
  variant = 'cards',
  label,
}) => {
  if (variant === 'dag') {
    return (
      <div className="flex flex-col h-full w-full rounded-2xl border border-slate-800 bg-slate-950/90 p-6 space-y-4 animate-fade-in">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2 text-indigo-400 text-xs font-semibold">
            <GitGraph className="h-4 w-4 animate-spin text-indigo-400" />
            <span>{label || 'Tejiendo grafo de precedencia causal y reduciendo transitividades...'}</span>
          </div>
          <div className="h-6 w-24 rounded-lg bg-slate-800 animate-pulse" />
        </div>
        <div className="flex-1 min-h-[400px] flex items-center justify-center">
          <div className="space-y-6 w-full max-w-lg">
            <div className="mx-auto h-12 w-48 rounded-xl bg-slate-800/80 animate-pulse" />
            <div className="flex justify-around">
              <div className="h-20 w-36 rounded-xl bg-slate-800/60 animate-pulse" />
              <div className="h-20 w-36 rounded-xl bg-slate-800/60 animate-pulse" />
            </div>
            <div className="flex justify-between">
              <div className="h-16 w-28 rounded-xl bg-slate-800/40 animate-pulse" />
              <div className="h-16 w-28 rounded-xl bg-slate-800/40 animate-pulse" />
              <div className="h-16 w-28 rounded-xl bg-slate-800/40 animate-pulse" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (variant === 'cockpit') {
    return (
      <div className="space-y-5 p-6 animate-fade-in">
        <div className="flex items-center gap-2 text-indigo-400 text-xs font-semibold py-1">
          <Brain className="h-4 w-4 animate-pulse text-indigo-400" />
          <span>{label || 'Ejecutando diagnóstico curricular y delimitación por contrato pedagógico...'}</span>
        </div>

        {/* Header Gauge Skeleton */}
        <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-5 flex items-center justify-between">
          <div className="space-y-2 w-1/2">
            <div className="h-3 w-28 rounded bg-slate-800 animate-pulse" />
            <div className="h-6 w-64 rounded bg-slate-800 animate-pulse" />
          </div>
          <div className="h-12 w-28 rounded-xl bg-slate-800 animate-pulse" />
        </div>

        {/* Prerequisites Skeleton */}
        <div className="space-y-3">
          <div className="h-4 w-48 rounded bg-slate-800 animate-pulse" />
          <div className="space-y-2">
            {Array.from({ length: 2 }).map((_, i) => (
              <div
                key={i}
                className="h-20 rounded-xl border border-slate-800/80 bg-slate-950/60 p-4 animate-pulse flex justify-between items-center"
              >
                <div className="space-y-2 w-2/3">
                  <div className="h-4 w-40 rounded bg-slate-800" />
                  <div className="h-3 w-64 rounded bg-slate-800/80" />
                </div>
                <div className="h-8 w-24 rounded-lg bg-slate-800" />
              </div>
            ))}
          </div>
        </div>

        {/* Themes Grid Skeleton */}
        <div className="space-y-3">
          <div className="h-4 w-36 rounded bg-slate-800 animate-pulse" />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="h-24 rounded-xl border border-slate-800/80 bg-slate-950/60 p-4 animate-pulse space-y-2"
              >
                <div className="h-4 w-32 rounded bg-slate-800" />
                <div className="h-3 w-full rounded bg-slate-800/70" />
                <div className="h-3 w-4/5 rounded bg-slate-800/70" />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (variant === 'table') {
    return (
      <div className="space-y-3 p-4 animate-fade-in">
        <div className="flex items-center gap-2 text-indigo-400 text-xs font-semibold py-1">
          <Layers className="h-4 w-4 animate-spin text-indigo-400" />
          <span>{label || 'Cargando datos del mazo...'}</span>
        </div>
        <div className="space-y-2">
          {Array.from({ length: count }).map((_, i) => (
            <div
              key={i}
              className="h-12 rounded-xl border border-slate-800 bg-slate-900/60 p-3 flex items-center justify-between animate-pulse"
            >
              <div className="h-4 w-1/3 rounded bg-slate-800" />
              <div className="h-4 w-20 rounded bg-slate-800" />
              <div className="h-4 w-16 rounded bg-slate-800" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Default: 'cards'
  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center gap-2 text-indigo-400 text-xs font-semibold py-1">
        <Sparkles className="h-4 w-4 animate-spin text-indigo-400" />
        <span>{label || 'Analizando el material y estructurando las flashcards con Active Recall...'}</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {Array.from({ length: count }).map((_, i) => (
          <div
            key={i}
            className="h-[280px] rounded-2xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-xl flex flex-col justify-between animate-pulse"
          >
            <div>
              {/* Header skeleton */}
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-2.5 mb-4">
                <div className="flex items-center gap-2">
                  <div className="h-5 w-5 rounded-full bg-slate-800" />
                  <div className="h-4 w-12 rounded-md bg-slate-800" />
                </div>
                <div className="h-4 w-8 rounded-md bg-slate-800" />
              </div>

              {/* Body lines */}
              <div className="space-y-2.5">
                <div className="h-4 w-5/6 rounded bg-slate-800" />
                <div className="h-4 w-full rounded bg-slate-800" />
                <div className="h-4 w-3/4 rounded bg-slate-800" />
              </div>
            </div>

            {/* Footer skeleton */}
            <div className="border-t border-slate-800/80 pt-3 flex items-center justify-between">
              <div className="flex gap-1">
                <div className="h-4 w-12 rounded bg-slate-800" />
                <div className="h-4 w-10 rounded bg-slate-800" />
              </div>
              <div className="h-7 w-24 rounded-xl bg-slate-800" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
