import React, { Suspense, lazy } from 'react';
import { Routes, Route } from 'react-router-dom';
import { Box, Flex, Spinner, Center } from '@chakra-ui/react';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import Devices from './pages/Devices';
import Discoveries from './pages/Discoveries';
import PathVisualizer from './pages/PathVisualizer';
import Settings from './pages/Settings';
import ChangeList from './pages/changes/ChangeList';
import ChangeDetail from './pages/changes/ChangeDetail';

const TopologyMap = lazy(() => import('./pages/topology/TopologyMap'));
const ComplianceViewer = lazy(() => import('./pages/compliance/ComplianceViewer'));
const AssistantPage = lazy(() => import('./pages/assistant/AssistantPage'));

const PageLoader = () => (
  <Center h="100%">
    <Spinner size="xl" color="blue.500" />
  </Center>
);

function App() {
  return (
    <Flex h="100vh">
      <Sidebar />
      <Box flex="1" overflow="auto" bg="gray.50">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/portal" element={<Dashboard />} />
          <Route path="/devices" element={<Devices />} />
          <Route path="/discoveries" element={<Discoveries />} />
          <Route path="/path-visualizer" element={<PathVisualizer />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/changes" element={<ChangeList />} />
          <Route path="/changes/:id" element={<ChangeDetail />} />
          <Route path="/topology" element={<Suspense fallback={<PageLoader />}><TopologyMap /></Suspense>} />
          <Route path="/compliance" element={<Suspense fallback={<PageLoader />}><ComplianceViewer /></Suspense>} />
          <Route path="/assistant" element={<Suspense fallback={<PageLoader />}><AssistantPage /></Suspense>} />
        </Routes>
      </Box>
    </Flex>
  );
}

export default App;
