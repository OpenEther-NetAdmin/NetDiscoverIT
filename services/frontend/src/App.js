import React, { Suspense, lazy } from 'react';
import { Routes, Route } from 'react-router-dom';
import { Box, Flex, Spinner, Center } from '@chakra-ui/react';
import { useAuth } from './context/AuthContext';
import Sidebar from './components/Sidebar';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './pages/Login';
import Register from './pages/Register';
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
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <Center h="100vh">
        <Spinner size="xl" color="blue.500" />
      </Center>
    );
  }

  return (
    <Flex h="100vh">
      {user && <Sidebar />}
      <Box flex="1" overflow="auto" bg="gray.50">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/portal"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/devices"
            element={
              <ProtectedRoute>
                <Devices />
              </ProtectedRoute>
            }
          />
          <Route
            path="/discoveries"
            element={
              <ProtectedRoute>
                <Discoveries />
              </ProtectedRoute>
            }
          />
          <Route
            path="/path-visualizer"
            element={
              <ProtectedRoute>
                <PathVisualizer />
              </ProtectedRoute>
            }
          />
          <Route
            path="/settings"
            element={
              <ProtectedRoute>
                <Settings />
              </ProtectedRoute>
            }
          />
          <Route
            path="/changes"
            element={
              <ProtectedRoute>
                <ChangeList />
              </ProtectedRoute>
            }
          />
          <Route
            path="/changes/:id"
            element={
              <ProtectedRoute>
                <ChangeDetail />
              </ProtectedRoute>
            }
          />
          <Route
            path="/topology"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <TopologyMap />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/compliance"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <ComplianceViewer />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/assistant"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <AssistantPage />
                </Suspense>
              </ProtectedRoute>
            }
          />
        </Routes>
      </Box>
    </Flex>
  );
}

export default App;
