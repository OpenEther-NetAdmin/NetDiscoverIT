import React, { useEffect, useRef, useState, useMemo } from 'react';
import * as d3 from 'd3';
import {
  Box, Flex, Heading, Input, InputGroup, InputLeftElement,
  Select, Button, Spinner, Text, Badge, Tag, TagLabel, Wrap, WrapItem,
} from '@chakra-ui/react';
import { FiSearch, FiRefreshCw } from 'react-icons/fi';
import { useTopology } from './useTopology';
import {
  getNodeStyle, getBadgeColor, truncate, COMPLIANCE_SCOPE_OPTIONS,
  initializeNodePositions, applyForceSimulation,
} from './topologyUtils';

const NODE_HEX_COLORS = {
  'blue.500': '#3182CE',
  'gray.500': '#718096',
  'red.500': '#E53E3E',
  'green.500': '#38A169',
  'gray.400': '#A0AEC0',
};

const BADGE_HEX_COLORS = {
  'orange.500': '#DD6B20',
  'purple.500': '#6B46C1',
  'yellow.500': '#D69E2E',
  'red.600': '#C53030',
  'blue.500': '#2B6CB0',
};

const LEGEND_TYPES = [
  { label: 'Router',   color: '#3182CE', shape: 'circle' },
  { label: 'Switch',   color: '#718096', shape: 'square' },
  { label: 'Firewall', color: '#E53E3E', shape: 'diamond' },
  { label: 'Server',   color: '#38A169', shape: 'square' },
  { label: 'Unknown',  color: '#A0AEC0', shape: 'circle' },
];

const LEGEND_SCOPES = [
  { label: 'PCI',      color: '#DD6B20' },
  { label: 'HIPAA',    color: '#6B46C1' },
  { label: 'SOX',      color: '#D69E2E' },
  { label: 'FedRAMP',  color: '#C53030' },
  { label: 'Other',    color: '#2B6CB0' },
];

function toHex(chakraColor) {
  return NODE_HEX_COLORS[chakraColor] || chakraColor;
}

function toBadgeHex(chakraColor) {
  return BADGE_HEX_COLORS[chakraColor] || chakraColor;
}

const TopologyMap = () => {
  const { nodes, edges, loading, error, selectedNode, selectNode, clearSelection, refresh } = useTopology();
  const svgRef = useRef(null);
  const [popoverPos, setPopoverPos] = useState({ x: 0, y: 0 });
  const [searchValue, setSearchValue] = useState('');
  const [scopeFilter, setScopeFilter] = useState('');

  const filteredNodes = useMemo(() => {
    let filtered = nodes;
    if (searchValue) {
      const lower = searchValue.toLowerCase();
      filtered = filtered.filter((n) => n.hostname?.toLowerCase().includes(lower));
    }
    if (scopeFilter) {
      filtered = filtered.filter(
        (n) => Array.isArray(n.compliance_scope) && n.compliance_scope.includes(scopeFilter)
      );
    }
    return filtered;
  }, [nodes, searchValue, scopeFilter]);

  const filteredEdges = useMemo(() => {
    const filteredIds = new Set(filteredNodes.map((n) => n.id));
    return edges.filter((e) => filteredIds.has(e.source) && filteredIds.has(e.target));
  }, [edges, filteredNodes]);

  useEffect(() => {
    if (!svgRef.current || loading || error || filteredNodes.length === 0) {
      return;
    }

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = svgRef.current.clientWidth || 800;
    const height = svgRef.current.clientHeight || 600;

    const g = svg.append('g');
    svg.call(
      d3.zoom().scaleExtent([0.2, 4]).on('zoom', (event) => {
        g.attr('transform', event.transform);
      })
    );

    const simNodes = initializeNodePositions(
      filteredNodes.map((n) => ({ ...n })),
      width,
      height,
    );
    const nodeById = Object.fromEntries(simNodes.map((n) => [n.id, n]));
    const simEdges = filteredEdges
      .filter((e) => nodeById[e.source] && nodeById[e.target])
      .map((e) => ({ source: nodeById[e.source], target: nodeById[e.target] }));

    const simulation = applyForceSimulation(simNodes, simEdges, width, height);

    const link = g
      .append('g')
      .attr('stroke', '#CBD5E0')
      .attr('stroke-width', 1.5)
      .selectAll('line')
      .data(simEdges)
      .join('line');

    const node = g
      .append('g')
      .selectAll('g')
      .data(simNodes)
      .join('g')
      .attr('cursor', 'pointer')
      .call(
        d3
          .drag()
          .on('start', (event, d) => {
            if (!event.active && simulation) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on('drag', (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on('end', (event, d) => {
            if (!event.active && simulation) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      )
      .on('click', (event, d) => {
        event.stopPropagation();
        if (!svgRef.current) return;
        const rect = svgRef.current.getBoundingClientRect();
        setPopoverPos({
          x: event.clientX - rect.left,
          y: event.clientY - rect.top,
        });
        selectNode(d);
      });

    node.each(function drawShape(d) {
      const el = d3.select(this);
      const style = getNodeStyle(d.device_type);
      const fillColor = toHex(style.fill);
      if (style.shape === 'circle') {
        el.append('circle')
          .attr('r', style.r)
          .attr('fill', fillColor)
          .attr('stroke', 'white')
          .attr('stroke-width', 2);
      } else if (style.shape === 'rect' || style.shape === 'wideRect') {
        const w = style.w || style.size;
        const h = style.h || style.size;
        el.append('rect')
          .attr('x', -w / 2)
          .attr('y', -h / 2)
          .attr('width', w)
          .attr('height', h)
          .attr('rx', 3)
          .attr('fill', fillColor)
          .attr('stroke', 'white')
          .attr('stroke-width', 2);
      } else if (style.shape === 'diamond') {
        el.append('rect')
          .attr('x', -style.size / 2)
          .attr('y', -style.size / 2)
          .attr('width', style.size)
          .attr('height', style.size)
          .attr('fill', fillColor)
          .attr('stroke', 'white')
          .attr('stroke-width', 2)
          .attr('transform', 'rotate(45)');
      }
    });

    node.each(function drawBadge(d) {
      const badgeColor = getBadgeColor(d.compliance_scope);
      if (badgeColor) {
        d3.select(this)
          .append('circle')
          .attr('cx', 14)
          .attr('cy', -14)
          .attr('r', 6)
          .attr('fill', toBadgeHex(badgeColor))
          .attr('stroke', 'white')
          .attr('stroke-width', 1.5);
      }
    });

    node
      .append('text')
      .attr('y', 28)
      .attr('text-anchor', 'middle')
      .attr('font-size', '10px')
      .attr('fill', '#4A5568')
      .attr('pointer-events', 'none')
      .text((d) => truncate(d.hostname, 12));

    if (simulation) {
      simulation.on('tick', () => {
        link
          .attr('x1', (d) => d.source.x)
          .attr('y1', (d) => d.source.y)
          .attr('x2', (d) => d.target.x)
          .attr('y2', (d) => d.target.y);
        node.attr('transform', (d) => `translate(${d.x},${d.y})`);
      });
    }

    svg.on('click', () => clearSelection());

    return () => {
      if (simulation) simulation.stop();
    };
  }, [filteredNodes, filteredEdges, loading, error, selectNode, clearSelection]);

  return (
    <Box p={6} h="100%" display="flex" flexDirection="column">
      <Flex justify="space-between" align="center" mb={4}>
        <Heading size="lg">Network Map</Heading>
        <Button leftIcon={<FiRefreshCw />} size="sm" onClick={refresh}>
          Refresh
        </Button>
      </Flex>

      <Flex gap={3} mb={4} flexWrap="wrap">
        <InputGroup maxW="240px">
          <InputLeftElement pointerEvents="none">
            <FiSearch color="gray" />
          </InputLeftElement>
          <Input
            placeholder="Search by hostname"
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
          />
        </InputGroup>
        <Select
          aria-label="Filter by compliance scope"
          maxW="200px"
          value={scopeFilter}
          onChange={(e) => setScopeFilter(e.target.value)}
        >
          <option value="">All scopes</option>
          {COMPLIANCE_SCOPE_OPTIONS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </Select>
      </Flex>

      <Box flex="1" position="relative" bg="white" borderRadius="md"
           border="1px" borderColor="gray.200" overflow="hidden" minHeight="400px">
        {loading && (
          <Flex position="absolute" inset={0} align="center" justify="center" zIndex={1}>
            <Spinner size="xl" />
          </Flex>
        )}

        {error && !loading && (
          <Flex position="absolute" inset={0} align="center" justify="center"
                direction="column" gap={3} zIndex={1}>
            <Text color="red.500">{error}</Text>
            <Button size="sm" onClick={refresh}>Retry</Button>
          </Flex>
        )}

        {!loading && !error && filteredNodes.length === 0 && (
          <Flex position="absolute" inset={0} align="center" justify="center" zIndex={1}>
            <Text color="gray.500">
              {nodes.length === 0
                ? 'No devices found. Run a discovery to populate your network map.'
                : 'No devices match the current filters.'}
            </Text>
          </Flex>
        )}

        <svg
          ref={svgRef}
          width="100%"
          height="100%"
          data-testid="topology-svg"
        />

        {selectedNode && (
          <Box
            position="absolute"
            left={`${popoverPos.x + 10}px`}
            top={`${popoverPos.y - 10}px`}
            bg="white"
            borderRadius="md"
            boxShadow="lg"
            border="1px"
            borderColor="gray.200"
            p={3}
            zIndex={10}
            minW="200px"
            maxW="260px"
          >
            <Text fontWeight="bold" mb={1}>{selectedNode.hostname}</Text>
            {selectedNode.management_ip && (
              <Text fontSize="sm" color="gray.600" mb={1}>{selectedNode.management_ip}</Text>
            )}
            <Badge colorScheme="blue" mb={2}>{selectedNode.device_type}</Badge>
            {selectedNode.compliance_scope?.length > 0 && (
              <Wrap mt={1}>
                {selectedNode.compliance_scope.map((s) => (
                  <WrapItem key={s}>
                    <Tag size="sm" colorScheme="orange"><TagLabel>{s}</TagLabel></Tag>
                  </WrapItem>
                ))}
              </Wrap>
            )}
          </Box>
        )}

        <Box
          position="absolute"
          bottom={3}
          left={3}
          bg="whiteAlpha.900"
          borderRadius="md"
          p={2}
          fontSize="10px"
          lineHeight="1.6"
          border="1px"
          borderColor="gray.100"
        >
          <Text fontWeight="bold" mb={1} color="gray.500">SHAPE = TYPE</Text>
          {LEGEND_TYPES.map(({ label, color }) => (
            <Flex key={label} align="center" gap={1} mb="1px">
              <Box w={3} h={3} borderRadius="50%" bg={color} flexShrink={0} />
              <Text color="gray.600">{label}</Text>
            </Flex>
          ))}
          <Text fontWeight="bold" mt={2} mb={1} color="gray.500">DOT = SCOPE</Text>
          {LEGEND_SCOPES.map(({ label, color }) => (
            <Flex key={label} align="center" gap={1} mb="1px">
              <Box w={2} h={2} borderRadius="50%" bg={color} flexShrink={0} />
              <Text color="gray.600">{label}</Text>
            </Flex>
          ))}
        </Box>
      </Box>
    </Box>
  );
};

export default TopologyMap;
