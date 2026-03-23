import React from 'react';
import { Routes, Route } from 'react-router-dom';
import { Box, Flex } from '@chakra-ui/react';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import Devices from './pages/Devices';
import Discoveries from './pages/Discoveries';
import PathVisualizer from './pages/PathVisualizer';
import Settings from './pages/Settings';

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
        </Routes>
      </Box>
    </Flex>
  );
}

export default App;
