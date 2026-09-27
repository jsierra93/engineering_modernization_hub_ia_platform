import { PageBlueprint, createFrontendPlugin } from '@backstage/frontend-plugin-api';
import { modhubAuthApi, modhubApi } from './apis';
import { rootRouteRef } from './routes';

// Inline rather than imported: a deep import from @material-ui/icons
// resolves under Node but not under the CLI's webpack from a plugin
// directory, and the sidebar only needs one glyph.
const ModernizacionesIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 6v3l4-4-4-4v3c-4.42 0-8 3.58-8 8 0 1.57.46 3.03 1.24 4.26L6.7 14.8A5.87 5.87 0 0 1 6 12c0-3.31 2.69-6 6-6zm6.76 1.74L17.3 9.2c.44.84.7 1.79.7 2.8 0 3.31-2.69 6-6 6v-3l-4 4 4 4v-3c4.42 0 8-3.58 8-8 0-1.57-.46-3.03-1.24-4.26z" />
  </svg>
);

const modernizacionesPage = PageBlueprint.make({
  params: {
    path: '/modhub',
    title: 'Modernizaciones',
    icon: <ModernizacionesIcon />,
    routeRef: rootRouteRef,
    loader: () =>
      import('./components/ModernizacionesPage').then(m => (
        <m.ModernizacionesPage />
      )),
  },
});

export default createFrontendPlugin({
  pluginId: 'modhub',
  extensions: [
    modernizacionesPage,
    modhubAuthApi,
    modhubApi,
  ],
});
