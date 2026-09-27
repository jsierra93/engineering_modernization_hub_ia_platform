import { useState } from 'react';
import useAsync from 'react-use/lib/useAsync';
import {
  Page,
  Header,
  Content,
  Table,
  TableColumn,
  Progress,
  ResponseErrorPanel,
  ContentHeader,
  SupportButton,
} from '@backstage/core-components';
import { useApi } from '@backstage/core-plugin-api';
import { Button, FormControlLabel, Switch } from '@material-ui/core';
import { modhubApiRef } from '../../apis';
import { Run } from '../../api/types';
import { CreateRunDialog } from '../CreateRunDialog';
import { ApprovalDialog } from '../ApprovalDialog';

const columns: TableColumn<Run>[] = [
  { title: 'Objetivo', field: 'objetivo' },
  { title: 'Repo', field: 'repo' },
  { title: 'Estado', field: 'status' },
  { title: 'Estrategia', field: 'strategy_id' },
  {
    title: 'Costo',
    field: 'spent_usd',
    render: (row: Run) => `$${row.spent_usd.toFixed(2)} / $${row.max_usd.toFixed(2)}`,
  },
  { title: 'Creado', field: 'created_at' },
];

const AWAITING_APPROVAL = 'AWAITING_APPROVAL';

/**
 * Fase 5, task 5.3. Reads real data from modhub/v1 (via modhub-backend's
 * proxy, task 5.2) -- no mock rows. `mine`/`status` filters mirror the
 * design artifact's stated CLI convention (`inbox` =
 * `mine=true&status=AWAITING_APPROVAL`), exposed here as a simple toggle
 * plus a status the user types, since a full filter bar was judged not
 * worth the extra UI for a "mínimo real" pass -- see the session's own
 * gap-analysis note on Fase 5's scope.
 */
export const ModernizacionesPage = () => {
  const modhubApi = useApi(modhubApiRef);
  const [mineOnly, setMineOnly] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [reviewing, setReviewing] = useState<Run | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const { value: runs, loading, error } = useAsync(
    async () => modhubApi.listRuns({ mine: mineOnly }),
    [modhubApi, mineOnly, refreshKey],
  );

  return (
    <Page themeId="tool">
      <Header title="Modernizaciones" subtitle="Engineering Modernization Hub" />
      <Content>
        <ContentHeader title="Runs">
          <FormControlLabel
            control={
              <Switch
                checked={mineOnly}
                onChange={event => setMineOnly(event.target.checked)}
              />
            }
            label="Solo mías"
          />
          <Button
            variant="contained"
            color="primary"
            onClick={() => setCreateOpen(true)}
            style={{ marginLeft: 16 }}
          >
            Nueva solicitud
          </Button>
          <SupportButton>
            Crea y sigue solicitudes de modernización sobre repos registrados.
          </SupportButton>
        </ContentHeader>
        {loading && <Progress />}
        {error && <ResponseErrorPanel error={error} />}
        {!loading && !error && (
          <Table
            title="Solicitudes"
            options={{ search: true, paging: true, pageSize: 10 }}
            columns={columns}
            data={runs ?? []}
            actions={[
              (row: Run) => ({
                icon: () => <Button size="small" color="primary">Revisar plan</Button>,
                tooltip: 'Revisar y aprobar o rechazar el plan propuesto',
                hidden: row.status !== AWAITING_APPROVAL,
                onClick: () => setReviewing(row),
              }),
            ]}
          />
        )}
        <ApprovalDialog
          run={reviewing}
          onClose={() => setReviewing(null)}
          onDecided={() => {
            setReviewing(null);
            setRefreshKey(key => key + 1);
          }}
        />
        <CreateRunDialog
          open={createOpen}
          onClose={() => setCreateOpen(false)}
          onCreated={() => {
            setCreateOpen(false);
            setRefreshKey(key => key + 1);
          }}
        />
      </Content>
    </Page>
  );
};
