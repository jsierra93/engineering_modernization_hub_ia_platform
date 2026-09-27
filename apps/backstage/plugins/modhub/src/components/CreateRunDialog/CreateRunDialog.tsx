import { useState } from 'react';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
} from '@material-ui/core';
import { useApi, alertApiRef } from '@backstage/core-plugin-api';
import { modhubApiRef } from '../../apis';

/**
 * Fase 5, task 5.3's "formulario de solicitud." Implemented as a plugin
 * dialog calling POST /modhub/v1/runs directly (via modhub-backend),
 * rather than a Scaffolder template/custom action -- a deliberate scope
 * cut, not an oversight: a Scaffolder action runs server-side under the
 * scaffolder-backend's OWN identity, and forwarding the initiator's raw
 * Cognito token through a scaffolder action requires a custom field
 * extension plus non-trivial identity plumbing that doesn't demonstrate
 * any control this dialog doesn't already exercise (the same
 * modhub-backend proxy, the same JWT, the same API). See the session's
 * gap-analysis note for the full reasoning.
 */
export interface CreateRunDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export const CreateRunDialog = ({ open, onClose, onCreated }: CreateRunDialogProps) => {
  const modhubApi = useApi(modhubApiRef);
  const alertApi = useApi(alertApiRef);
  const [submitting, setSubmitting] = useState(false);
  const [repo, setRepo] = useState('');
  const [commit, setCommit] = useState('');
  const [objetivo, setObjetivo] = useState('');
  const [maxUsd, setMaxUsd] = useState('2');
  const [maxIterations, setMaxIterations] = useState('3');
  const [maxMinutes, setMaxMinutes] = useState('20');
  const [excludedPaths, setExcludedPaths] = useState('');

  const submit = async () => {
    setSubmitting(true);
    try {
      const created = await modhubApi.createRun({
        repo,
        commit,
        objetivo,
        max_usd: Number(maxUsd),
        max_iterations: Number(maxIterations),
        max_minutes: Number(maxMinutes),
        restricciones: {
          excluded_paths: excludedPaths
            .split(/\r?\n/)
            .map(line => line.trim())
            .filter(Boolean),
        },
      });
      alertApi.post({
        message: `Run ${created.run_id} creado (${created.resolved_strategy.id}).`,
        severity: 'success',
      });
      onCreated();
    } catch (e) {
      alertApi.post({ message: (e as Error).message, severity: 'error' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Nueva solicitud de modernización</DialogTitle>
      <DialogContent>
        <TextField
          label="Repositorio"
          placeholder="octocat/Hello-World"
          fullWidth
          margin="dense"
          value={repo}
          onChange={e => setRepo(e.target.value)}
        />
        <TextField
          label="Commit (SHA de 40 caracteres)"
          fullWidth
          margin="dense"
          value={commit}
          onChange={e => setCommit(e.target.value)}
        />
        <TextField
          label="Objetivo"
          placeholder="migrar pydantic v1 a v2"
          fullWidth
          margin="dense"
          value={objetivo}
          onChange={e => setObjetivo(e.target.value)}
        />
        <TextField
          label="Presupuesto máximo (USD)"
          type="number"
          margin="dense"
          value={maxUsd}
          onChange={e => setMaxUsd(e.target.value)}
        />
        <TextField
          label="Iteraciones de fix máximas"
          type="number"
          margin="dense"
          value={maxIterations}
          onChange={e => setMaxIterations(e.target.value)}
        />
        <TextField
          label="Minutos máximos"
          type="number"
          margin="dense"
          value={maxMinutes}
          onChange={e => setMaxMinutes(e.target.value)}
        />
        <TextField
          label="Rutas excluidas (una por línea)"
          placeholder={'src/legacy/**\ntests/fixtures/**'}
          fullWidth
          multiline
          minRows={2}
          margin="dense"
          helperText="Patrones glob que el agente no podrá modificar, aunque la estrategia los permita."
          value={excludedPaths}
          onChange={e => setExcludedPaths(e.target.value)}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button color="primary" variant="contained" disabled={submitting} onClick={submit}>
          Crear
        </Button>
      </DialogActions>
    </Dialog>
  );
};
