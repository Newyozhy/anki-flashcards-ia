import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertOctagon, RefreshCw, Download, RotateCcw, ChevronDown, ChevronUp } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
  onReset?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  isDetailsExpanded: boolean;
  backupSuccess: boolean;
}

export class AppErrorBoundary extends Component<Props, State> {
  public override state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
    isDetailsExpanded: false,
    backupSuccess: false,
  };

  public static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  public override componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('AppErrorBoundary caught an unhandled rendering error:', error, errorInfo);
    this.setState({ errorInfo });
  }

  private handleRetry = () => {
    if (this.props.onReset) {
      this.props.onReset();
    }
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      isDetailsExpanded: false,
      backupSuccess: false,
    });
  };

  private handleHardReload = () => {
    window.location.reload();
  };

  private handleClearCacheAndReload = () => {
    try {
      sessionStorage.removeItem('ankicraft_active_inspection');
      sessionStorage.removeItem('ankicraft_sanitation_queue');
    } catch {
      // Ignored
    }
    window.location.reload();
  };

  private handleExportBackup = () => {
    try {
      const cardsRaw = localStorage.getItem('ankicraft_generated_cards');
      const cards = cardsRaw ? JSON.parse(cardsRaw) : [];
      const backupData = {
        exported_at: new Date().toISOString(),
        cards,
        raw_text: sessionStorage.getItem('ankicraft_raw_text') || '',
        audit_report: localStorage.getItem('ankicraft_audit_report')
          ? JSON.parse(localStorage.getItem('ankicraft_audit_report')!)
          : null,
      };

      const blob = new Blob([JSON.stringify(backupData, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ankicraft_recovery_backup_${Date.now()}.json`;
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(url);
      document.body.removeChild(a);

      this.setState({ backupSuccess: true });
    } catch (e) {
      console.error('Error exporting recovery backup:', e);
    }
  };

  public override render() {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          aria-live="assertive"
          className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-4 sm:p-6"
        >
          <div className="w-full max-w-2xl rounded-2xl border border-rose-500/40 bg-gradient-to-b from-rose-950/40 via-slate-900 to-slate-950 p-6 sm:p-8 shadow-2xl shadow-rose-950/40 space-y-6">
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-rose-500/15 border border-rose-500/30 text-rose-400">
                <AlertOctagon className="h-6 w-6" />
              </div>
              <div className="flex-1 min-w-0">
                <span className="text-[10px] font-bold uppercase tracking-wider text-rose-400 bg-rose-500/10 border border-rose-500/20 px-2 py-0.5 rounded-full">
                  Recuperación ante Fallos
                </span>
                <h1 className="text-lg sm:text-xl font-bold text-white mt-1">
                  {this.props.fallbackTitle || 'Se produjo un error inesperado en la interfaz'}
                </h1>
                <p className="text-xs sm:text-sm text-slate-300 mt-1 leading-relaxed">
                  React detuvo el renderizado para proteger tus datos. Tus flashcards guardadas y tu texto
                  siguen a salvo en el almacenamiento local de tu navegador.
                </p>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex flex-wrap items-center gap-2.5 pt-2 border-t border-slate-800">
              <button
                type="button"
                onClick={this.handleRetry}
                className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-4 py-2.5 text-xs shadow-md shadow-indigo-600/30 transition-all active:scale-95 cursor-pointer"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                <span>Reintentar Renderizado</span>
              </button>

              <button
                type="button"
                onClick={this.handleExportBackup}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-800/80 hover:bg-slate-700 text-slate-200 hover:text-white px-3.5 py-2.5 text-xs font-semibold transition-all cursor-pointer"
                title="Descargar tus tarjetas actuales a un archivo JSON"
              >
                <Download className="h-3.5 w-3.5 text-indigo-400" />
                <span>{this.state.backupSuccess ? '✓ Copia Descargada' : 'Descargar Copia de Seguridad'}</span>
              </button>

              <button
                type="button"
                onClick={this.handleHardReload}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-800/80 hover:bg-slate-700 text-slate-200 hover:text-white px-3.5 py-2.5 text-xs font-semibold transition-all cursor-pointer"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                <span>Recargar Página</span>
              </button>

              <button
                type="button"
                onClick={this.handleClearCacheAndReload}
                className="inline-flex items-center gap-1.5 text-xs text-rose-400 hover:text-rose-300 hover:underline px-2 py-1 ml-auto cursor-pointer"
                title="Limpia datos temporales de sesión si hay un plan dañado"
              >
                <span>Limpiar sesión corrupta</span>
              </button>
            </div>

            {/* Diagnostic Details Accordion */}
            <div className="rounded-xl border border-slate-800 bg-slate-950/60 overflow-hidden">
              <button
                type="button"
                onClick={() => this.setState((prev) => ({ isDetailsExpanded: !prev.isDetailsExpanded }))}
                className="w-full flex items-center justify-between px-4 py-2.5 text-left text-xs font-semibold text-slate-400 hover:text-slate-200 cursor-pointer"
              >
                <span>Detalles técnicos del fallo</span>
                {this.state.isDetailsExpanded ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </button>

              {this.state.isDetailsExpanded && (
                <div className="px-4 pb-4 space-y-2 border-t border-slate-800/60 pt-3">
                  <p className="text-xs font-mono text-rose-300 break-words">
                    {this.state.error?.toString()}
                  </p>
                  {this.state.errorInfo?.componentStack && (
                    <pre className="text-[11px] font-mono text-slate-400 bg-slate-900/90 rounded-lg p-3 overflow-x-auto max-h-48 whitespace-pre leading-relaxed border border-slate-800">
                      {this.state.errorInfo.componentStack}
                    </pre>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
