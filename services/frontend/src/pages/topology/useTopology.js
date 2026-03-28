import { useState, useEffect, useCallback } from 'react';
import api from '../../services/api';

export function useTopology() {
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);

  const fetchTopology = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getTopology();
      setNodes(data.nodes || []);
      setEdges(data.edges || []);
    } catch (err) {
      setError(err.message || 'Failed to load topology data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTopology();
  }, [fetchTopology]);

  const selectNode = useCallback((node) => {
    setSelectedNode(node);
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedNode(null);
  }, []);

  const refresh = useCallback(() => {
    fetchTopology();
  }, [fetchTopology]);

  return {
    nodes,
    edges,
    loading,
    error,
    selectedNode,
    selectNode,
    clearSelection,
    refresh,
  };
}

export default useTopology;
