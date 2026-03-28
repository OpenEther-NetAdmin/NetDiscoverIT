import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box, Flex, Text, Badge, IconButton, Spinner, Button,
  Heading, Tag, TagLabel, Wrap, WrapItem,
  Divider, useDisclosure, useToast,
  Code, Collapse,
} from '@chakra-ui/react';
import { FiMaximize2, FiExternalLink, FiChevronDown, FiChevronUp, FiArrowLeft } from 'react-icons/fi';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import TransitionModal from './TransitionModal';

const LIFECYCLE_STEPS = ['draft', 'proposed', 'approved', 'implemented', 'verified'];

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

const LifecycleStepper = ({ status }) => {
  const currentIndex = LIFECYCLE_STEPS.indexOf(status);
  return (
    <Flex align="center" gap={2} flexWrap="wrap" mb={4}>
      {LIFECYCLE_STEPS.map((step, index) => {
        const isDone = index < currentIndex;
        const isCurrent = step === status;
        return (
          <React.Fragment key={step}>
            <Badge
              colorScheme={isDone ? 'green' : isCurrent ? STATUS_COLORS[status] || 'blue' : 'gray'}
              variant={isCurrent ? 'solid' : 'subtle'}
              textTransform="capitalize"
              px={2} py={1}
            >
              {isDone ? `✓ ${step}` : step}
            </Badge>
            {index < LIFECYCLE_STEPS.length - 1 && (
              <Text color="gray.400" fontSize="sm" lineHeight="1">→</Text>
            )}
          </React.Fragment>
        );
      })}
      {status === 'rolled_back' && (
        <Badge colorScheme="red" variant="solid" px={2} py={1}>rolled back</Badge>
      )}
    </Flex>
  );
};

const ChangeDetail = ({ id: propId, isDrawer = false }) => {
  const params = useParams();
  const id = propId || params.id;
  const navigate = useNavigate();
  const { user } = useAuth();
  const toast = useToast();
  const { isOpen: isModalOpen, onOpen: onModalOpen, onClose: onModalClose } = useDisclosure();
  const [change, setChange] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);
  const [simExpanded, setSimExpanded] = useState(false);

  const loadChange = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getChange(id);
      setChange(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (id) loadChange();
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  const openAction = (action) => {
    setPendingAction(action);
    onModalOpen();
  };

  const handleTransition = async (text) => {
    if (!pendingAction) return;
    setActionLoading(true);
    try {
      if (pendingAction === 'propose') await api.proposeChange(id);
      else if (pendingAction === 'approve') await api.approveChange(id, { notes: text });
      else if (pendingAction === 'implement') await api.implementChange(id, { implementation_evidence: text });
      else if (pendingAction === 'verify') await api.verifyChange(id, { verification_results: text });
      else if (pendingAction === 'rollback') await api.rollbackChange(id, { rollback_evidence: text });
      toast({ title: 'Change updated', status: 'success', duration: 3000, isClosable: true });
      onModalClose();
      await loadChange();
    } catch (err) {
      toast({ title: 'Action failed', description: err.message, status: 'error', duration: 5000, isClosable: true });
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <Flex justify="center" align="center" h="200px">
        <Spinner />
      </Flex>
    );
  }

  if (error || !change) {
    return (
      <Box p={4}>
        <Text color="red.500">{error || 'Change not found'}</Text>
        <Button mt={2} size="sm" onClick={loadChange}>Retry</Button>
      </Box>
    );
  }

  const userRole = user?.role || 'viewer';
  const action = getActionForStatus(change.status, userRole);
  const canRollback = ['admin', 'msp_admin'].includes(userRole) && !['verified', 'rolled_back'].includes(change.status);

  return (
    <Box p={isDrawer ? 4 : 6}>
      {/* Header */}
      <Flex align="center" justify="space-between" mb={4}>
        <Flex align="center" gap={3}>
          {!isDrawer && (
            <IconButton
              icon={<FiArrowLeft />}
              aria-label="back to changes"
              variant="ghost"
              size="sm"
              onClick={() => navigate('/changes')}
            />
          )}
          <Box>
            <Flex align="center" gap={2}>
              <Text fontWeight="bold" fontSize="lg">{change.change_number}</Text>
              <Badge colorScheme={STATUS_COLORS[change.status] || 'gray'} variant="solid">
                {change.status}
              </Badge>
              <Badge colorScheme={RISK_COLORS[change.risk_level] || 'gray'} variant="outline">
                {change.risk_level}
              </Badge>
            </Flex>
            <Text fontSize="sm" color="gray.600" mt={1}>{change.change_type}</Text>
          </Box>
        </Flex>
        {isDrawer && (
          <IconButton
            icon={<FiMaximize2 />}
            aria-label="expand to full page"
            variant="ghost"
            size="sm"
            onClick={() => navigate(`/changes/${id}`)}
          />
        )}
      </Flex>

      {/* 1. Lifecycle stepper */}
      <LifecycleStepper status={change.status} />

      {/* 2. Metadata */}
      <Heading size="sm" mb={2}>Details</Heading>
      <Box bg="gray.50" borderRadius="md" p={3} mb={4}>
        <Text fontWeight="semibold" mb={1}>{change.title}</Text>
        <Text fontSize="sm" color="gray.600">{change.description}</Text>
      </Box>

      {/* 3. Affected devices */}
      {change.affected_devices?.length > 0 && (
        <Box mb={4}>
          <Text fontSize="sm" fontWeight="semibold" color="gray.500" mb={1}>AFFECTED DEVICES</Text>
          <Wrap>
            {change.affected_devices.map((devId) => (
              <WrapItem key={devId}>
                <Tag size="sm" colorScheme="blue">
                  <TagLabel>{String(devId).slice(0, 8)}…</TagLabel>
                </Tag>
              </WrapItem>
            ))}
          </Wrap>
        </Box>
      )}

      {/* 4. Compliance scopes */}
      {change.affected_compliance_scopes?.length > 0 && (
        <Box mb={4}>
          <Text fontSize="sm" fontWeight="semibold" color="gray.500" mb={1}>COMPLIANCE SCOPES</Text>
          <Wrap>
            {change.affected_compliance_scopes.map((scope) => (
              <WrapItem key={scope}>
                <Tag size="sm" colorScheme="orange"><TagLabel>{scope}</TagLabel></Tag>
              </WrapItem>
            ))}
          </Wrap>
        </Box>
      )}

      {/* 5. Simulation */}
      {change.simulation_performed && (
        <Box mb={4}>
          <Text fontSize="sm" fontWeight="semibold" color="gray.500" mb={1}>SIMULATION</Text>
          <Flex align="center" gap={2}>
            <Badge colorScheme={change.simulation_passed ? 'green' : 'red'}>
              {change.simulation_passed ? 'simulation passed' : 'simulation failed'}
            </Badge>
            {change.simulation_results && (
              <Button size="xs" variant="ghost" onClick={() => setSimExpanded(!simExpanded)}>
                {simExpanded ? <FiChevronUp /> : <FiChevronDown />}
              </Button>
            )}
          </Flex>
          <Collapse in={simExpanded}>
            <Code display="block" whiteSpace="pre" mt={2} p={2} fontSize="xs" borderRadius="md">
              {JSON.stringify(change.simulation_results, null, 2)}
            </Code>
          </Collapse>
        </Box>
      )}

      {/* 6. External ticket */}
      {change.external_ticket_url && (
        <Box mb={4}>
          <Text fontSize="sm" fontWeight="semibold" color="gray.500" mb={1}>EXTERNAL TICKET</Text>
          <Flex align="center" gap={1}>
            <Text fontSize="sm">{change.external_ticket_id}</Text>
            <IconButton
              as="a"
              href={change.external_ticket_url}
              target="_blank"
              rel="noopener noreferrer"
              icon={<FiExternalLink />}
              aria-label="open ticket"
              variant="ghost"
              size="xs"
            />
          </Flex>
        </Box>
      )}

      {/* 7. Evidence */}
      {(change.pre_change_hash || change.post_change_hash || change.implementation_evidence || change.verification_results) && (
        <Box mb={4}>
          <Text fontSize="sm" fontWeight="semibold" color="gray.500" mb={1}>EVIDENCE</Text>
          <Box fontSize="xs" color="gray.600">
            {change.pre_change_hash && <Text>Pre-change hash: <Code>{change.pre_change_hash.slice(0, 12)}…</Code></Text>}
            {change.post_change_hash && <Text>Post-change hash: <Code>{change.post_change_hash.slice(0, 12)}…</Code></Text>}
            {change.implementation_evidence && <Text mt={1}>{change.implementation_evidence}</Text>}
            {change.verification_results && <Text mt={1}>{change.verification_results}</Text>}
          </Box>
        </Box>
      )}

      {/* 8. Action button */}
      <Divider mb={4} />
      <Flex gap={2}>
        {action && (
          <Button colorScheme={STATUS_COLORS[change.status] || 'blue'} flex="1" onClick={() => openAction(action)}>
            {action.charAt(0).toUpperCase() + action.slice(1)}
          </Button>
        )}
        {canRollback && (
          <Button colorScheme="red" variant="outline" onClick={() => openAction('rollback')}>
            Rollback
          </Button>
        )}
      </Flex>

      <TransitionModal
        isOpen={isModalOpen}
        onClose={onModalClose}
        onConfirm={handleTransition}
        action={pendingAction}
        changeNumber={change.change_number}
        isLoading={actionLoading}
      />
    </Box>
  );
};

export default ChangeDetail;
