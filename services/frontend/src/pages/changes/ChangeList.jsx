import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Flex, Heading, Text, Badge, Button, Spinner,
  Select, Input, InputGroup, InputLeftElement,
  Card, CardBody, Wrap, WrapItem, Tag, TagLabel,
  useDisclosure, useToast,
} from '@chakra-ui/react';
import { FiSearch, FiRefreshCw, FiExternalLink } from 'react-icons/fi';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useOrg } from '../../context/OrgContext';
import ChangeDrawer from './ChangeDrawer';
import TransitionModal from './TransitionModal';

const STATUS_COLORS = {
  draft: 'gray', proposed: 'yellow', approved: 'green',
  implemented: 'purple', verified: 'teal', rolled_back: 'red',
};
const RISK_COLORS = { low: 'green', medium: 'orange', high: 'red', critical: 'red' };

function getActionForStatus(status, role) {
  const isAdmin = ['admin', 'msp_admin'].includes(role);
  const isEngineer = ['engineer', 'admin', 'msp_admin'].includes(role);
  if (status === 'draft' && isEngineer) return 'propose';
  if (status === 'proposed' && isAdmin) return 'approve';
  if (status === 'approved' && isEngineer) return 'implement';
  if (status === 'implemented' && isAdmin) return 'verify';
  return null;
}

const ChangeList = () => {
  const { user } = useAuth();
  const { activeOrg } = useOrg();
  const toast = useToast();
  const { isOpen: isDrawerOpen, onOpen: onDrawerOpen, onClose: onDrawerClose } = useDisclosure();
  const { isOpen: isModalOpen, onOpen: onModalOpen, onClose: onModalClose } = useDisclosure();

  const [changes, setChanges] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [riskFilter, setRiskFilter] = useState('');
  const [search, setSearch] = useState('');
  const [selectedChange, setSelectedChange] = useState(null);
  const [pendingAction, setPendingAction] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);

  const loadChanges = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getChanges({ status: statusFilter, risk_level: riskFilter });
      setChanges(data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, riskFilter]);

  useEffect(() => {
    loadChanges();
  }, [loadChanges, activeOrg]);

  const openDrawer = (change) => {
    setSelectedChange(change);
    onDrawerOpen();
  };

  const openAction = (e, change, action) => {
    e.stopPropagation();
    setSelectedChange(change);
    setPendingAction(action);
    onModalOpen();
  };

  const handleTransition = async (text) => {
    if (!pendingAction || !selectedChange) return;
    setActionLoading(true);
    try {
      const id = selectedChange.id;
      if (pendingAction === 'propose') await api.proposeChange(id);
      else if (pendingAction === 'approve') await api.approveChange(id, { notes: text });
      else if (pendingAction === 'implement') await api.implementChange(id, { implementation_evidence: text });
      else if (pendingAction === 'verify') await api.verifyChange(id, { verification_results: text });
      else if (pendingAction === 'rollback') await api.rollbackChange(id, { rollback_evidence: text });
      toast({ title: 'Change updated', status: 'success', duration: 3000, isClosable: true });
      onModalClose();
      await loadChanges();
    } catch (err) {
      toast({ title: 'Action failed', description: err.message, status: 'error', duration: 5000, isClosable: true });
    } finally {
      setActionLoading(false);
    }
  };

  const filtered = changes.filter((c) => {
    const matchesStatus = !statusFilter || c.status === statusFilter;
    const matchesRisk = !riskFilter || c.risk_level === riskFilter;
    const matchesSearch = !search ||
      c.title?.toLowerCase().includes(search.toLowerCase()) ||
      c.change_number?.toLowerCase().includes(search.toLowerCase());
    return matchesStatus && matchesRisk && matchesSearch;
  });

  const userRole = user?.role || 'viewer';

  if (loading) {
    return (
      <Box p={6}>
        <Flex justify="center" align="center" h="400px"><Spinner size="xl" /></Flex>
      </Box>
    );
  }

  if (error) {
    return (
      <Box p={6}>
        <Text color="red.500">{error}</Text>
        <Button mt={4} onClick={loadChanges}>Retry</Button>
      </Box>
    );
  }

  return (
    <Box p={6}>
      <Flex justify="space-between" align="center" mb={6}>
        <Heading size="lg">Changes</Heading>
        <Button leftIcon={<FiRefreshCw />} size="sm" onClick={loadChanges}>Refresh</Button>
      </Flex>

      <Flex gap={3} mb={6} flexWrap="wrap">
        <InputGroup maxW="280px">
          <InputLeftElement pointerEvents="none"><FiSearch color="gray.300" /></InputLeftElement>
          <Input
            placeholder="Search by title or number"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </InputGroup>
        <Select
          aria-label="Filter by status"
          maxW="180px"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All statuses</option>
          {['draft', 'proposed', 'approved', 'implemented', 'verified', 'rolled_back'].map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </Select>
        <Select
          aria-label="Filter by risk"
          maxW="160px"
          value={riskFilter}
          onChange={(e) => setRiskFilter(e.target.value)}
        >
          <option value="">All risks</option>
          {['low', 'medium', 'high', 'critical'].map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </Select>
      </Flex>

      {filtered.length === 0 ? (
        <Box textAlign="center" py={12} color="gray.500">
          No changes found. Adjust filters or create a new change.
        </Box>
      ) : (
        <Flex direction="column" gap={3}>
          {filtered.map((change) => {
            const action = getActionForStatus(change.status, userRole);
            return (
              <Card
                key={change.id}
                cursor="pointer"
                _hover={{ borderColor: 'blue.300', shadow: 'sm' }}
                borderWidth="1px"
                onClick={() => openDrawer(change)}
              >
                <CardBody>
                  <Flex justify="space-between" align="flex-start">
                    <Box flex="1" mr={4}>
                      <Flex align="center" gap={2} mb={1} flexWrap="wrap">
                        <Badge colorScheme="blue" variant="outline" fontSize="xs" fontWeight="bold">
                          {change.change_number}
                        </Badge>
                        <Badge colorScheme={STATUS_COLORS[change.status] || 'gray'} variant="solid" fontSize="xs">
                          {change.status}
                        </Badge>
                        <Badge colorScheme={RISK_COLORS[change.risk_level] || 'gray'} variant="outline" fontSize="xs">
                          {change.risk_level}
                        </Badge>
                      </Flex>
                      <Text fontWeight="semibold" mb={2}>{change.title}</Text>
                      <Flex align="center" gap={3} flexWrap="wrap">
                        <Text fontSize="xs" color="gray.500">
                          {change.affected_devices?.length || 0} device{change.affected_devices?.length !== 1 ? 's' : ''}
                        </Text>
                        {change.affected_compliance_scopes?.length > 0 && (
                          <Wrap spacing={1}>
                            {change.affected_compliance_scopes.map((scope) => (
                              <WrapItem key={scope}>
                                <Tag size="sm" colorScheme="orange"><TagLabel>{scope}</TagLabel></Tag>
                              </WrapItem>
                            ))}
                          </Wrap>
                        )}
                        {change.simulation_performed && (
                          <Badge colorScheme={change.simulation_passed ? 'green' : 'red'} variant="subtle" fontSize="xs">
                            {change.simulation_passed ? '✓ sim' : '✗ sim'}
                          </Badge>
                        )}
                        {change.external_ticket_url && (
                          <Flex
                            as="a"
                            href={change.external_ticket_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            align="center"
                            gap={1}
                            color="blue.500"
                            fontSize="xs"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <FiExternalLink size={10} />
                            <Text>{change.external_ticket_id || 'ticket'}</Text>
                          </Flex>
                        )}
                      </Flex>
                    </Box>
                    {action && (
                      <Button
                        colorScheme={STATUS_COLORS[change.status] || 'blue'}
                        size="sm"
                        flexShrink={0}
                        onClick={(e) => openAction(e, change, action)}
                      >
                        {action.charAt(0).toUpperCase() + action.slice(1)}
                      </Button>
                    )}
                  </Flex>
                </CardBody>
              </Card>
            );
          })}
        </Flex>
      )}

      <ChangeDrawer
        changeId={selectedChange?.id}
        isOpen={isDrawerOpen}
        onClose={onDrawerClose}
        statusHint={selectedChange?.status}
        changeNumberHint={selectedChange?.change_number}
      />

      <TransitionModal
        isOpen={isModalOpen}
        onClose={onModalClose}
        onConfirm={handleTransition}
        action={pendingAction}
        changeNumber={selectedChange?.change_number}
        isLoading={actionLoading}
      />
    </Box>
  );
};

export default ChangeList;
