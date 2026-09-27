import { useState } from 'react';
import useAsync from 'react-use/lib/useAsync';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Typography,
} from '@material-ui/core';
import { Progress, ResponseErrorPanel } from '@backstage/core-components';
import { alertApiRef, useApi } from '@backstage/core-plugin-api';
import { modhubApiRef } from '../../apis';

type Props = {
  runId: string | null;
  onClose: () => void;
};

export const ReportDialog = ({ runId, onClose }: Props) => {
  const modhubApi = useApi(modhubApiRef);
  const alertApi = useApi(alertApiRef);
  const [publishing, setPublishing] = useState(false);
  const [prUrl, setPrUrl] = useState<string | null>(null);
  const { value: report, loading, error } = useAsync(
    async () => (runId ? modhubApi.getReport(runId) : undefined),
    [modhubApi, runId],
  );

  if (!runId) {
    return null;
  }

  const publish = async () => {
    if (!runId) {
      return;
    }
    setPublishing(true);
    try {
      const created = await modhubApi.openPullRequest(runId);
      setPrUrl(created.pull_request_url);
      alertApi.post({ message: `PR creado: ${created.pull_request_url}`, severity: 'success' });
    } catch (caught) {
      alertApi.post({
        message: caught instanceof Error ? caught.message : String(caught),
        severity: 'error',
      });
    } finally {
      setPublishing(false);
    }
  };

  const download = () => {
    if (!report?.diff) {
      return;
    }
    const url = URL.createObjectURL(new Blob([report.diff], { type: 'text/x-patch' }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `modhub-${report.run_id.slice(0, 8)}.patch`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Dialog open onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Informe de modernización</DialogTitle>
      <DialogContent>
        {loading && <Progress />}
        {error && <ResponseErrorPanel error={error} />}

        {report && (
          <>
            <Typography variant="body2" color="textSecondary">
              {report.repo} @ {report.commit.slice(0, 12)}
            </Typography>
            <Typography variant="h6" style={{ marginTop: 8 }}>
              {report.verdict.status}
            </Typography>
            <Typography variant="body2">
              ${report.verdict.spent_usd.toFixed(4)} de ${report.verdict.max_usd.toFixed(2)} ·{' '}
              {report.verdict.iterations_used}/{report.verdict.max_iterations} iteraciones ·{' '}
              estrategia {report.strategy.id}
            </Typography>

            <Divider style={{ margin: '16px 0' }} />

            <Typography variant="subtitle2">Qué se hizo</Typography>
            <Typography variant="body2">{report.narrative.summary}</Typography>

            {(report.narrative.sources ?? []).length > 0 && (
              <>
                <Typography variant="subtitle2" style={{ marginTop: 16 }}>
                  Fuentes consultadas
                </Typography>
                <ul style={{ marginTop: 4 }}>
                  {(report.narrative.sources ?? []).map(source => (
                    <li key={source}>
                      <a href={source} target="_blank" rel="noreferrer">
                        {source}
                      </a>
                    </li>
                  ))}
                </ul>
              </>
            )}

            <Typography variant="subtitle2" style={{ marginTop: 16 }}>
              Archivos modificados ({report.changed_paths.length})
            </Typography>
            <ul style={{ marginTop: 4 }}>
              {report.changed_paths.map(path => (
                <li key={path}>
                  <code>{path}</code>
                </li>
              ))}
            </ul>

            <Typography variant="subtitle2" style={{ marginTop: 16 }}>
              Modelos usados
            </Typography>
            <Typography variant="body2">
              {Object.entries(report.models_used)
                .map(([phase, model]) => `${phase}: ${model}`)
                .join(' · ') || '—'}
            </Typography>

            {report.diff && (
              <>
                <Typography variant="subtitle2" style={{ marginTop: 16 }}>
                  Diff
                </Typography>
                <pre
                  style={{
                    maxHeight: 320,
                    overflow: 'auto',
                    fontSize: 12,
                    background: 'rgba(0,0,0,0.25)',
                    padding: 12,
                  }}
                >
                  {report.diff}
                </pre>
              </>
            )}
          </>
        )}
      </DialogContent>
      <DialogActions>
        {prUrl && (
          <Button href={prUrl} target="_blank" color="primary">
            Abrir PR
          </Button>
        )}
        <Button onClick={onClose}>Cerrar</Button>
        <Button onClick={download} color="primary" disabled={!report?.diff}>
          Descargar parche
        </Button>
        <Button
          onClick={publish}
          color="primary"
          variant="contained"
          disabled={publishing || !!prUrl || !report?.changed_paths.length}
        >
          {publishing ? 'Creando PR...' : 'Crear PR'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
