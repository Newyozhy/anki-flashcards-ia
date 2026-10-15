import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import {
  Layers,
  ShieldCheck,
  AlertTriangle,
  AlertCircle,
  Folder,
  FolderOpen,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Search,
  BookmarkPlus,
  X,
  Loader2,
  RefreshCw,
  HelpCircle,
  Sparkles,
  ListFilter,
  ChevronDown,
  ChevronsDown,
  ChevronsUp,
} from 'lucide-react';
import { api } from '../services/api';
import { SocraticNodeMasteryModal } from './SocraticNodeMasteryModal';
import { PedagogicalOrderAuditModal } from './PedagogicalOrderAuditModal';
import type {
  DeckCoverageMapResponse,
  DeckCoverageMapNode,
  DeckConceptDAG,
  ConceptNode,
} from '../types';

interface CognitivePrecedenceDAGProps {
  deckName: string;
  apiKey?: string;
  onEnqueueGap?: (gapTitle: string, reason: string) => void;
  onEnqueueNote?: (noteId: number, label: string) => void;
  onInspectNote?: (noteId: number, label: string) => void;
  initialMap?: DeckCoverageMapResponse | null;
  targetConcept?: string;
}

type NodeFilter = 'all' | 'unreviewed' | 'bad' | 'optimal' | 'gap';

interface PlacedNode {
  node: DeckCoverageMapNode;
  x: number;
  y: number;
  width: number;
  height: number;
}

export const CognitivePrecedenceDAG: React.FC<CognitivePrecedenceDAGProps> = ({
  deckName,
  apiKey,
  onEnqueueGap,
  onEnqueueNote,
  onInspectNote,
  initialMap,
  targetConcept,
}) => {
  const [localMapOverride, setLocalMapOverride] = useState<{
    deckName: string;
    sourceMap: DeckCoverageMapResponse | null | undefined;
    data: DeckCoverageMapResponse;
  } | null>(null);
  const mapData =
    localMapOverride &&
    localMapOverride.deckName === deckName &&
    localMapOverride.sourceMap === initialMap
      ? localMapOverride.data
      : initialMap || null;
  const [dagData, setDagData] = useState<DeckConceptDAG | null>(null);
  const [selectedConceptNode, setSelectedConceptNode] = useState<ConceptNode | null>(null);

  const [isLoading, setIsLoading] = useState<boolean>(!initialMap);
  const [isWeavingDAG, setIsWeavingDAG] = useState<boolean>(false);
  const [weavingMessage, setWeavingMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Socratic Mastery State
  const [isSocraticModalOpen, setIsSocraticModalOpen] = useState<boolean>(false);
  const [socraticConceptName, setSocraticConceptName] = useState<string>('');

  // Pedagogical Order Audit Modal State
  const [isAuditModalOpen, setIsAuditModalOpen] = useState<boolean>(false);

  // View Mode: DAG Graph vs Card List
  const [viewMode, setViewMode] = useState<'graph' | 'list'>('graph');

  // Filters & Search
  const [filter, setFilter] = useState<NodeFilter>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedNode, setSelectedNode] = useState<DeckCoverageMapNode | null>(null);

  // Pan & Zoom
  const [zoom, setZoom] = useState<number>(0.9);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 50, y: 30 });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const dragStartRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  // Fetch coverage map and DAG in parallel (G-08)
  const fetchBothData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [mapResult, dagResult] = await Promise.allSettled([
        api.getDeckCoverageMap(deckName, apiKey),
        api.getDeckConceptDAG(deckName),
      ]);

      if (mapResult.status === 'fulfilled') {
        setLocalMapOverride({ deckName, sourceMap: initialMap, data: mapResult.value });
      }
      if (dagResult.status === 'fulfilled') {
        setDagData(dagResult.value);
      }
      if (mapResult.status === 'rejected' && dagResult.status === 'rejected') {
        setError(`Error al cargar datos de '${deckName}'`);
      }
    } catch (err: any) {
      setError(err.message || `Error al obtener el mapa de cobertura y DAG de '${deckName}'`);
    } finally {
      setIsLoading(false);
    }
  }, [deckName, apiKey, initialMap]);

  // Alias for backward compatibility
  const fetchCoverageMap = fetchBothData;

  // Weave DAG Ontological Edges iteratively until exhaustion (G-11)
  const handleWeaveDAG = async () => {
    setIsWeavingDAG(true);
    setWeavingMessage(null);
    setError(null);

    let totalProcessed = 0;
    let keepGoing = true;

    try {
      while (keepGoing) {
        setWeavingMessage(`Tejiendo ontología del mazo... (Procesadas: ${totalProcessed} notas)`);
        const res = await api.extractDeckOntology(
          deckName,
          { batch_size: 10 },
          apiKey
        );

        totalProcessed += res.processed_notes_count;
        const remaining = res.remaining_unextracted_count ?? 0;

        setWeavingMessage(
          `Tejidas ${totalProcessed} notas. Restantes por procesar: ${remaining}. Conceptos en DAG: ${res.dag_summary?.total_concepts ?? 0}`
        );

        // Terminate loop cleanly when all notes are woven or batch produced 0
        if (remaining === 0 || res.processed_notes_count === 0) {
          keepGoing = false;
        }
      }

      await fetchBothData();
    } catch (err: any) {
      setError(err.message || 'Error al tejer aristas ontológicas del DAG');
    } finally {
      setIsWeavingDAG(false);
    }
  };

  useEffect(() => {
    if (!initialMap) {
      const timer = setTimeout(() => {
        void fetchBothData();
      }, 0);
      return () => clearTimeout(timer);
    } else {
      void api.getDeckConceptDAG(deckName).then(setDagData).catch(() => {});
    }
  }, [initialMap, fetchBothData, deckName]);

  // Layout calculation
  const layout = useMemo(() => {
    if (!mapData || mapData.nodes.length === 0) {
      return { placedNodes: [], edges: [], width: 800, height: 600 };
    }

    const rootNode = mapData.nodes.find((n) => n.type === 'deck') || {
      id: `deck:${deckName}`,
      label: deckName,
      type: 'deck' as const,
      health: 'optimal' as const,
    };

    const clusterNodes = mapData.nodes.filter((n) => n.type === 'cluster');

    // Build children mapping for each cluster
    const clusterChildrenMap: Record<string, DeckCoverageMapNode[]> = {};
    clusterNodes.forEach((c) => {
      clusterChildrenMap[c.id] = [];
    });

    const nodeById = new Map(mapData.nodes.map((n) => [n.id, n]));

    mapData.edges.forEach((edge) => {
      if (clusterChildrenMap[edge.source]) {
        const targetNode = nodeById.get(edge.target);
        if (targetNode) {
          // Check filter
          const matchesFilter =
            filter === 'all' ||
            (filter === 'optimal' && targetNode.health === 'optimal') ||
            (filter === 'bad' && (targetNode.health === 'bad' || targetNode.health === 'debt' || targetNode.health === 'broken')) ||
            (filter === 'gap' && targetNode.health === 'gap') ||
            (filter === 'unreviewed' && targetNode.health === 'unreviewed');

          const matchesSearch =
            !searchQuery.trim() ||
            targetNode.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
            (targetNode.details &&
              targetNode.details.toLowerCase().includes(searchQuery.toLowerCase()));

          if (matchesFilter && matchesSearch) {
            clusterChildrenMap[edge.source].push(targetNode);
          }
        }
      }
    });

    // Filter out clusters with 0 children when filtering (unless filter is 'all')
    const activeClusters = clusterNodes.filter((c) => {
      if (filter === 'all' && !searchQuery.trim()) return true;
      return (clusterChildrenMap[c.id] || []).length > 0;
    });

    const colWidth = 240;
    const colGap = 40;
    const nodeWidth = 220;
    const nodeHeight = 56;
    const clusterNodeHeight = 44;
    const rootNodeHeight = 48;

    const totalCols = Math.max(1, activeClusters.length);
    const totalWidth = Math.max(900, totalCols * (colWidth + colGap) + 100);

    const placed: PlacedNode[] = [];
    const placedEdges: {
      sourceX: number;
      sourceY: number;
      targetX: number;
      targetY: number;
      type: 'root-cluster' | 'cluster-leaf';
      health: string;
    }[] = [];

    // Place Root Node
    const rootX = totalWidth / 2 - nodeWidth / 2;
    const rootY = 40;
    placed.push({
      node: rootNode,
      x: rootX,
      y: rootY,
      width: nodeWidth,
      height: rootNodeHeight,
    });

    let maxBottomY = rootY + rootNodeHeight;

    // Place Clusters & their children
    activeClusters.forEach((cluster, colIdx) => {
      const colStartX = 50 + colIdx * (colWidth + colGap);
      const clusterX = colStartX + (colWidth - nodeWidth) / 2;
      const clusterY = 150;

      placed.push({
        node: cluster,
        x: clusterX,
        y: clusterY,
        width: nodeWidth,
        height: clusterNodeHeight,
      });

      // Edge from Root to Cluster
      placedEdges.push({
        sourceX: rootX + nodeWidth / 2,
        sourceY: rootY + rootNodeHeight,
        targetX: clusterX + nodeWidth / 2,
        targetY: clusterY,
        type: 'root-cluster',
        health: cluster.health,
      });

      // Place children vertically under this cluster
      const children = clusterChildrenMap[cluster.id] || [];
      children.forEach((child, rowIdx) => {
        const childX = clusterX;
        const childY = clusterY + clusterNodeHeight + 35 + rowIdx * (nodeHeight + 16);

        placed.push({
          node: child,
          x: childX,
          y: childY,
          width: nodeWidth,
          height: nodeHeight,
        });

        // Edge from Cluster to Child
        placedEdges.push({
          sourceX: clusterX + nodeWidth / 2,
          sourceY: clusterY + clusterNodeHeight,
          targetX: childX + nodeWidth / 2,
          targetY: childY,
          type: 'cluster-leaf',
          health: child.health,
        });

        if (childY + nodeHeight > maxBottomY) {
          maxBottomY = childY + nodeHeight;
        }
      });
    });

    const totalHeight = Math.max(650, maxBottomY + 80);

    return {
      placedNodes: placed,
      edges: placedEdges,
      width: totalWidth,
      height: totalHeight,
    };
  }, [mapData, filter, searchQuery, deckName]);

  // Concept Node Styles helper based on formal lifecycle status (G-08)
  const getConceptNodeStyles = (status?: string) => {
    switch (status) {
      case 'MASTERED':
        return {
          bg: 'fill-amber-950/40 stroke-amber-400',
          textColor: 'text-amber-200',
          badgeBg: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
          badgeLabel: 'Dominado',
        };
      case 'EXPANDED':
        return {
          bg: 'fill-purple-950/40 stroke-purple-400',
          textColor: 'text-purple-200',
          badgeBg: 'bg-purple-500/20 text-purple-300 border-purple-500/40',
          badgeLabel: 'Expandido',
        };
      case 'SUFFICIENT':
        return {
          bg: 'fill-emerald-950/40 stroke-emerald-400',
          textColor: 'text-emerald-200',
          badgeBg: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
          badgeLabel: 'Suficiente',
        };
      case 'SANITIZED':
        return {
          bg: 'fill-blue-950/40 stroke-blue-400',
          textColor: 'text-blue-200',
          badgeBg: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
          badgeLabel: 'Saneado',
        };
      case 'UNMAPPED':
        return {
          bg: 'fill-slate-900/60 stroke-slate-600',
          textColor: 'text-slate-400',
          badgeBg: 'bg-slate-800 text-slate-400 border-slate-700',
          badgeLabel: 'Sin Mapear',
        };
      case 'RAW':
      default:
        return {
          bg: 'fill-yellow-950/40 stroke-yellow-500',
          textColor: 'text-yellow-200',
          badgeBg: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40',
          badgeLabel: 'En Deuda',
        };
    }
  };

  // Precedence DAG Layout (G-08: Stratified by depth_level generations)
  const dagLayout = useMemo(() => {
    if (!dagData || !dagData.nodes || dagData.nodes.length === 0) {
      return { placedNodes: [], edges: [], width: 800, height: 600, levels: [] };
    }

    // Filter concepts if search query present
    const q = searchQuery.toLowerCase().trim();
    const filteredConcepts = q
      ? dagData.nodes.filter(
          (n) =>
            n.name.toLowerCase().includes(q) ||
            n.id.toLowerCase().includes(q) ||
            (n.taxonomy_path || '').toLowerCase().includes(q)
        )
      : dagData.nodes;

    // Group nodes by depth_level
    const nodesByLevel: Record<number, ConceptNode[]> = {};
    filteredConcepts.forEach((n) => {
      const lvl = n.depth_level ?? 0;
      if (!nodesByLevel[lvl]) nodesByLevel[lvl] = [];
      nodesByLevel[lvl].push(n);
    });

    const sortedLevels = Object.keys(nodesByLevel)
      .map(Number)
      .sort((a, b) => a - b);

    const colWidth = 260;
    const colGap = 80;
    const nodeWidth = 240;
    const nodeHeight = 72;
    const rowGap = 20;

    const placedNodesMap = new Map<
      string,
      { node: ConceptNode; x: number; y: number; width: number; height: number }
    >();
    let maxBottomY = 400;

    sortedLevels.forEach((level, colIdx) => {
      const colX = 60 + colIdx * (colWidth + colGap);
      const levelNodes = nodesByLevel[level];

      levelNodes.forEach((node, rowIdx) => {
        const nodeY = 80 + rowIdx * (nodeHeight + rowGap);
        placedNodesMap.set(node.id, {
          node,
          x: colX,
          y: nodeY,
          width: nodeWidth,
          height: nodeHeight,
        });

        if (nodeY + nodeHeight > maxBottomY) {
          maxBottomY = nodeY + nodeHeight;
        }
      });
    });

    const placedEdges: {
      sourceX: number;
      sourceY: number;
      targetX: number;
      targetY: number;
      relationType: string;
    }[] = [];

    (dagData.edges || []).forEach((edge) => {
      const srcPlaced = placedNodesMap.get(edge.source);
      const tgtPlaced = placedNodesMap.get(edge.target);
      if (srcPlaced && tgtPlaced) {
        placedEdges.push({
          sourceX: srcPlaced.x + nodeWidth,
          sourceY: srcPlaced.y + nodeHeight / 2,
          targetX: tgtPlaced.x,
          targetY: tgtPlaced.y + nodeHeight / 2,
          relationType: edge.relation_type,
        });
      }
    });

    const totalWidth = Math.max(900, 60 + sortedLevels.length * (colWidth + colGap) + 120);
    const totalHeight = Math.max(600, maxBottomY + 100);

    return {
      placedNodes: Array.from(placedNodesMap.values()),
      edges: placedEdges,
      width: totalWidth,
      height: totalHeight,
      levels: sortedLevels.map((lvl, idx) => ({
        level: lvl,
        x: 60 + idx * (colWidth + colGap),
        count: nodesByLevel[lvl].length,
      })),
    };
  }, [dagData, searchQuery]);

  // Flashcards mapped to the currently selected ConceptNode (crosses DAG with MapData)
  const conceptMappedCards = useMemo(() => {
    if (!selectedConceptNode || !mapData || !mapData.nodes) return [];
    const targetIds = new Set(selectedConceptNode.cards_mapped || []);
    return mapData.nodes.filter((n) => n.note_id && targetIds.has(n.note_id));
  }, [selectedConceptNode, mapData]);

  // Auto-focus and center on targetConcept when provided
  const hasFocusedTargetRef = useRef<string | null>(null);

  useEffect(() => {
    if (!targetConcept || !layout.placedNodes.length) return;
    if (hasFocusedTargetRef.current === targetConcept) return;

    const cleanTarget = targetConcept.toLowerCase().trim();
    const match = layout.placedNodes.find((pn) => {
      const lbl = pn.node.label.toLowerCase().trim();
      const det = (pn.node.details || '').toLowerCase().trim();
      const id = pn.node.id.toLowerCase().trim();
      return (
        (lbl.length >= 3 && (lbl.includes(cleanTarget) || cleanTarget.includes(lbl))) ||
        (det.length >= 4 && (det.includes(cleanTarget) || cleanTarget.includes(det))) ||
        id.includes(cleanTarget)
      );
    });

    if (match && containerRef.current) {
      hasFocusedTargetRef.current = targetConcept;
      setSelectedNode(match.node);
      const cWidth = containerRef.current.clientWidth || 800;
      const cHeight = containerRef.current.clientHeight || 550;
      setPan({
        x: Math.round(cWidth / 2 - (match.x + match.width / 2) * zoom),
        y: Math.round(cHeight / 2 - (match.y + match.height / 2) * zoom),
      });
    }
  }, [targetConcept, layout.placedNodes, zoom]);

  // Filtered items (notes & gaps) for List View
  const filteredItems = useMemo(() => {
    if (!mapData) return [];
    return mapData.nodes.filter((node) => {
      // List view displays study items: cards ('note') and curriculum gaps ('gap')
      if (node.type !== 'note' && node.type !== 'gap') return false;

      const isGap = node.type === 'gap' || node.health === 'gap';
      const isBad = node.health === 'bad' || node.health === 'debt' || node.health === 'broken';
      const isOptimal = node.health === 'optimal';
      const isUnreviewed = node.health === 'unreviewed';

      let matchesFilter = false;
      if (filter === 'all') {
        matchesFilter = true;
      } else if (filter === 'gap') {
        matchesFilter = isGap;
      } else if (filter === 'bad') {
        matchesFilter = isBad;
      } else if (filter === 'optimal') {
        matchesFilter = isOptimal;
      } else if (filter === 'unreviewed') {
        matchesFilter = isUnreviewed;
      }

      const q = searchQuery.toLowerCase().trim();
      const matchesSearch =
        !q ||
        node.label.toLowerCase().includes(q) ||
        (node.details && node.details.toLowerCase().includes(q)) ||
        (node.note_id && node.note_id.toString().includes(q)) ||
        node.id.toLowerCase().includes(q);

      return matchesFilter && matchesSearch;
    });
  }, [mapData, filter, searchQuery]);

  // Backward-compatible alias
  const filteredNotes = filteredItems;

  // Grouped themes for Accordion List View
  interface ThemeGroup {
    clusterId: string;
    clusterLabel: string;
    items: DeckCoverageMapNode[];
    optimalCount: number;
    badCount: number;
    unreviewedCount: number;
    gapCount: number;
  }

  const groupedThemes = useMemo(() => {
    if (!mapData) return [];

    const clusterNodes = new Map<string, DeckCoverageMapNode>();
    mapData.nodes.forEach((n) => {
      if (n.type === 'cluster') {
        clusterNodes.set(n.id, n);
      }
    });

    const targetToCluster = new Map<string, { id: string; label: string }>();
    mapData.edges.forEach((edge) => {
      const cluster = clusterNodes.get(edge.source);
      if (cluster) {
        targetToCluster.set(edge.target, { id: cluster.id, label: cluster.label });
      }
    });

    const groupsMap = new Map<string, ThemeGroup>();

    // Pre-populate with known clusters to preserve layout order
    clusterNodes.forEach((cluster) => {
      groupsMap.set(cluster.id, {
        clusterId: cluster.id,
        clusterLabel: cluster.label,
        items: [],
        optimalCount: 0,
        badCount: 0,
        unreviewedCount: 0,
        gapCount: 0,
      });
    });

    const unassignedGroup: ThemeGroup = {
      clusterId: 'cluster:unassigned',
      clusterLabel: 'Ejes Generales / Sin Eje Asignado',
      items: [],
      optimalCount: 0,
      badCount: 0,
      unreviewedCount: 0,
      gapCount: 0,
    };

    filteredItems.forEach((item) => {
      const clusterInfo = targetToCluster.get(item.id);
      const group = clusterInfo ? (groupsMap.get(clusterInfo.id) || unassignedGroup) : unassignedGroup;

      group.items.push(item);
      if (item.health === 'gap' || item.type === 'gap') {
        group.gapCount += 1;
      } else if (item.health === 'bad' || item.health === 'debt' || item.health === 'broken') {
        group.badCount += 1;
      } else if (item.health === 'optimal') {
        group.optimalCount += 1;
      } else {
        group.unreviewedCount += 1;
      }
    });

    const result: ThemeGroup[] = [];
    groupsMap.forEach((group) => {
      if (group.items.length > 0) {
        result.push(group);
      }
    });

    if (unassignedGroup.items.length > 0) {
      result.push(unassignedGroup);
    }

    return result;
  }, [mapData, filteredItems]);

  const [collapsedClusters, setCollapsedClusters] = useState<Record<string, boolean>>({});

  const toggleCluster = (clusterId: string) => {
    setCollapsedClusters((prev) => ({
      ...prev,
      [clusterId]: !prev[clusterId],
    }));
  };

  const expandAllClusters = () => {
    setCollapsedClusters({});
  };

  const collapseAllClusters = () => {
    const allCollapsed: Record<string, boolean> = {};
    groupedThemes.forEach((g) => {
      allCollapsed[g.clusterId] = true;
    });
    setCollapsedClusters(allCollapsed);
  };

  // Mouse handlers for dragging/panning
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return; // Only left click
    setIsDragging(true);
    dragStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setPan({
      x: e.clientX - dragStartRef.current.x,
      y: e.clientY - dragStartRef.current.y,
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleResetZoom = () => {
    setZoom(0.9);
    setPan({ x: 50, y: 30 });
  };

  const getNodeStyles = (node: DeckCoverageMapNode) => {
    if (node.type === 'deck') {
      const isUnreviewed = node.health === 'unreviewed';
      return {
        bg: isUnreviewed ? 'fill-slate-900 stroke-slate-600' : 'fill-slate-900 stroke-indigo-500',
        strokeWidth: 2,
        badgeBg: isUnreviewed
          ? 'bg-slate-800 text-slate-400 border-slate-700'
          : 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30',
        textColor: isUnreviewed ? 'text-slate-300' : 'text-indigo-200',
      };
    }
    if (node.type === 'cluster') {
      if (node.health === 'gap') {
        return {
          bg: 'fill-slate-900/95 stroke-rose-500/70',
          strokeWidth: 1.5,
          badgeBg: 'bg-rose-950/50 text-rose-300 border-rose-500/30',
          textColor: 'text-slate-100',
        };
      }
      if (node.health === 'bad' || node.health === 'debt' || node.health === 'broken') {
        return {
          bg: 'fill-slate-900/95 stroke-rose-500/70',
          strokeWidth: 1.5,
          badgeBg: 'bg-rose-950/50 text-rose-300 border-rose-500/30',
          textColor: 'text-slate-100',
        };
      }
      if (node.health === 'optimal') {
        return {
          bg: 'fill-slate-900/95 stroke-emerald-500/70',
          strokeWidth: 1.5,
          badgeBg: 'bg-emerald-950/50 text-emerald-300 border-emerald-500/30',
          textColor: 'text-slate-100',
        };
      }
      return {
        bg: 'fill-slate-900/95 stroke-slate-700',
        strokeWidth: 1.5,
        badgeBg: 'bg-slate-800 text-slate-400 border-slate-700',
        textColor: 'text-slate-300',
      };
    }
    if (node.health === 'gap') {
      return {
        bg: 'fill-rose-950/40 stroke-rose-500',
        strokeWidth: 1.5,
        dash: '4,4',
        badgeBg: 'bg-rose-500/20 text-rose-300 border-rose-500/30',
        textColor: 'text-rose-200',
      };
    }
    if (node.health === 'bad' || node.health === 'broken' || node.health === 'debt') {
      return {
        bg: 'fill-rose-950/40 stroke-rose-500',
        strokeWidth: 1.5,
        badgeBg: 'bg-rose-500/20 text-rose-300 border-rose-500/30',
        textColor: 'text-rose-200',
      };
    }
    if (node.health === 'unreviewed') {
      return {
        bg: 'fill-slate-900/90 stroke-slate-700',
        strokeWidth: 1.5,
        badgeBg: 'bg-slate-800 text-slate-400 border-slate-700',
        textColor: 'text-slate-300',
      };
    }
    // Optimal
    return {
      bg: 'fill-emerald-950/30 stroke-emerald-500',
      strokeWidth: 1.5,
      badgeBg: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
      textColor: 'text-emerald-200',
    };
  };

  return (
    <div className="relative flex flex-col h-full w-full rounded-2xl border border-slate-800 bg-slate-950/90 overflow-hidden shadow-2xl">
      {/* Top Filter & KPI Bar */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 border-b border-slate-800 p-4 bg-slate-900/70 backdrop-blur-md">
        {/* KPI Counts & Mode Switcher */}
        <div className="flex items-center gap-3 flex-wrap">
          {/* View Mode Toggle */}
          <div className="flex items-center rounded-xl border border-slate-700 bg-slate-950/80 p-1 text-xs shadow-xs">
            <button
              type="button"
              onClick={() => setViewMode('graph')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                viewMode === 'graph'
                  ? 'bg-indigo-600 text-white shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Layers className="h-3.5 w-3.5" />
              <span>Grafo DAG</span>
            </button>
            <button
              type="button"
              onClick={() => setViewMode('list')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                viewMode === 'list'
                  ? 'bg-indigo-600 text-white shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <ListFilter className="h-3.5 w-3.5" />
              <span>Lista ({filteredNotes.length})</span>
            </button>
          </div>

          {mapData && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="inline-flex items-center gap-1 rounded-full bg-slate-800 border border-slate-700 px-2 py-0.5 text-[10px] font-bold text-slate-300">
                <HelpCircle className="h-3 w-3 text-slate-400" />
                {mapData.unreviewed_count ?? 0} Sin Evaluar
              </span>
              {((mapData.bad_count ?? 0) + (mapData.debt_count ?? 0) + (mapData.broken_count ?? 0)) > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/10 border border-rose-500/30 px-2 py-0.5 text-[10px] font-bold text-rose-400">
                  <AlertTriangle className="h-3 w-3" />
                  {(mapData.bad_count ?? 0) + (mapData.debt_count ?? 0) + (mapData.broken_count ?? 0)} Mala
                </span>
              )}
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-bold text-emerald-400">
                <ShieldCheck className="h-3 w-3" />
                {mapData.optimal_count} Óptimas
              </span>
              <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/10 border border-rose-500/30 px-2 py-0.5 text-[10px] font-bold text-rose-400">
                <AlertCircle className="h-3 w-3" />
                {mapData.gap_count} Brechas
              </span>
            </div>
          )}
        </div>

        {/* Filter & Search Bar */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Search Box */}
          <div className="relative">
            <Search className="h-3.5 w-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              aria-label={viewMode === 'graph' ? 'Buscar nodo en el grafo' : 'Buscar tarjetas en el inventario'}
              placeholder={viewMode === 'graph' ? 'Buscar en grafo...' : 'Buscar tarjetas...'}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-8 pl-8 pr-3 rounded-lg border border-slate-700 bg-slate-800/80 text-xs text-slate-200 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none w-36 sm:w-44"
            />
          </div>

          {/* Filter Pills */}
          <div className="flex items-center rounded-lg border border-slate-700 bg-slate-800/90 p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setFilter('all')}
              className={`px-2 py-1 rounded text-[11px] font-semibold transition-all cursor-pointer ${
                filter === 'all'
                  ? 'bg-indigo-600 text-white shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Todas
            </button>
            <button
              type="button"
              onClick={() => setFilter('unreviewed')}
              className={`px-2 py-1 rounded text-[11px] font-semibold transition-all cursor-pointer ${
                filter === 'unreviewed'
                  ? 'bg-slate-700 text-white shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Sin Evaluar
            </button>
            <button
              type="button"
              onClick={() => setFilter('bad')}
              className={`px-2 py-1 rounded text-[11px] font-semibold transition-all cursor-pointer ${
                filter === 'bad'
                  ? 'bg-rose-600 text-white shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Mala
            </button>
            <button
              type="button"
              onClick={() => setFilter('optimal')}
              className={`px-2 py-1 rounded text-[11px] font-semibold transition-all cursor-pointer ${
                filter === 'optimal'
                  ? 'bg-emerald-600 text-white shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Óptimas
            </button>
            <button
              type="button"
              onClick={() => setFilter('gap')}
              className={`px-2 py-1 rounded text-[11px] font-semibold transition-all cursor-pointer ${
                filter === 'gap'
                  ? 'bg-rose-600 text-white shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Brechas
            </button>
          </div>

          {/* Refresh Button */}
          <button
            type="button"
            onClick={fetchCoverageMap}
            disabled={isLoading || isWeavingDAG}
            aria-label="Refrescar grafo e inventario"
            className="p-1.5 rounded-lg border border-slate-700 hover:bg-slate-800 text-slate-300 transition-colors cursor-pointer"
            title="Refrescar grafo e inventario"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>

          {/* Weave DAG Ontological Edges Button */}
          <button
            type="button"
            onClick={handleWeaveDAG}
            disabled={isWeavingDAG || isLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-indigo-500/40 bg-indigo-500/10 hover:bg-indigo-500/25 text-indigo-300 text-xs font-bold transition-all cursor-pointer shadow-xs disabled:opacity-50"
            title="Extraer ontología y tejer aristas de precedencia curricular en el DAG"
          >
            {isWeavingDAG ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />
            ) : (
              <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
            )}
            <span>{isWeavingDAG ? 'Tejiendo...' : 'Tejer DAG'}</span>
          </button>

          {/* Pedagogical Order Audit Button */}
          <button
            type="button"
            onClick={() => setIsAuditModalOpen(true)}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/10 hover:bg-emerald-500/25 text-emerald-300 text-xs font-bold transition-all cursor-pointer shadow-xs disabled:opacity-50"
            title="Auditar y asegurar el orden pedagógico (Nivel 0 -> Nivel 1) en Anki"
          >
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
            <span>Auditar Orden Anki</span>
          </button>
        </div>
      </div>


      {weavingMessage && (
        <div className="bg-indigo-950/60 border-b border-indigo-500/30 px-4 py-2 text-xs text-indigo-300 flex items-center justify-between">
          <span>✨ {weavingMessage}</span>
          <button
            type="button"
            onClick={() => setWeavingMessage(null)}
            aria-label="Cerrar notificación de tejido DAG"
            className="text-slate-400 hover:text-white"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Content Area: Graph Mode vs Card List Mode */}
      {viewMode === 'graph' ? (
        <div
          ref={containerRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        className={`relative flex-1 w-full min-h-[480px] overflow-hidden bg-radial from-slate-900/60 to-slate-950 ${
          isDragging ? 'cursor-grabbing' : 'cursor-grab'
        }`}
      >
        {isLoading && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-slate-950/70 backdrop-blur-xs space-y-3">
            <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
            <p className="text-xs font-semibold text-slate-300">
              Construyendo Grafo de Precedencia y Salud Cognitiva...
            </p>
          </div>
        )}

        {error && (
          <div className="absolute inset-0 z-20 flex items-center justify-center p-6 bg-slate-950/80">
            <div className="max-w-md rounded-xl border border-rose-500/40 bg-rose-950/40 p-4 text-xs text-rose-300 space-y-2 text-center">
              <AlertCircle className="h-6 w-6 text-rose-400 mx-auto" />
              <p className="font-bold">Error al cargar grafo de cobertura</p>
              <p>{error}</p>
              <button
                type="button"
                onClick={fetchCoverageMap}
                className="mt-2 rounded-lg bg-rose-600 px-3 py-1 text-xs font-semibold text-white"
              >
                Reintentar
              </button>
            </div>
          </div>
        )}

        {!isLoading && !error && layout.placedNodes.length === 0 && (
          <div className="absolute inset-0 z-20 flex items-center justify-center p-6 bg-slate-950/80">
            <div className="max-w-md rounded-2xl border border-dashed border-slate-800 bg-slate-900/60 p-8 text-center space-y-3">
              <Layers className="h-10 w-10 text-indigo-400 mx-auto" />
              <h3 className="text-sm font-bold text-white">Este mazo aún no tiene conceptos indexados en el DAG</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Para visualizar el árbol de precedencia cognitiva, asegurate de que el mazo tenga tarjetas y hacé clic en "Tejer DAG" arriba.
              </p>
              <button
                type="button"
                onClick={handleWeaveDAG}
                disabled={isWeavingDAG}
                className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-4 py-2 text-xs shadow-md shadow-indigo-600/30 transition-all cursor-pointer"
              >
                <Sparkles className="h-4 w-4" />
                <span>Tejer DAG Ontológico Ahora</span>
              </button>
            </div>
          </div>
        )}

        <svg
          width="100%"
          height="100%"
          className="select-none"
          style={{ minHeight: '480px' }}
        >
          <defs>
            {/* Grid Pattern */}
            <pattern id="dag-grid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path
                d="M 40 0 L 0 0 0 40"
                fill="none"
                stroke="rgba(255, 255, 255, 0.03)"
                strokeWidth="1"
              />
            </pattern>
            {/* Arrow Marker */}
            <marker
              id="arrowhead"
              markerWidth="6"
              markerHeight="6"
              refX="5"
              refY="3"
              orient="auto"
            >
              <polygon points="0 0, 6 3, 0 6" fill="#64748b" />
            </marker>
          </defs>

          {/* Grid Background */}
          <rect width="100%" height="100%" fill="url(#dag-grid)" />

          {/* Transform Container */}
          <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
            {dagData && dagData.nodes && dagData.nodes.length > 0 ? (
              <>
                {/* Stratified Level Column Headers (G-08) */}
                {dagLayout.levels.map((lvl) => (
                  <g key={`level-header-${lvl.level}`} transform={`translate(${lvl.x}, 25)`}>
                    <rect
                      width="240"
                      height="34"
                      rx="8"
                      className="fill-slate-900/90 stroke-slate-700/80"
                    />
                    <text
                      x="12"
                      y="22"
                      className="fill-indigo-300 font-mono text-xs font-bold"
                    >
                      NIVEL {lvl.level}
                    </text>
                    <text
                      x="228"
                      y="22"
                      textAnchor="end"
                      className="fill-slate-400 font-mono text-[11px]"
                    >
                      {lvl.count} {lvl.count === 1 ? 'concepto' : 'conceptos'}
                    </text>
                  </g>
                ))}

                {/* Render DAG Precedence Edges (Bézier curves) */}
                {dagLayout.edges.map((edge, idx) => {
                  const dx = edge.targetX - edge.sourceX;
                  const cx1 = edge.sourceX + Math.max(30, dx * 0.45);
                  const cx2 = edge.targetX - Math.max(30, dx * 0.45);
                  const pathD = `M ${edge.sourceX} ${edge.sourceY} C ${cx1} ${edge.sourceY}, ${cx2} ${edge.targetY}, ${edge.targetX} ${edge.targetY}`;

                  return (
                    <path
                      key={`dag-edge-${idx}`}
                      d={pathD}
                      fill="none"
                      stroke="rgba(99, 102, 241, 0.45)"
                      strokeWidth="2"
                      markerEnd="url(#arrowhead)"
                      className="transition-colors hover:stroke-indigo-400"
                    />
                  );
                })}

                {/* Render Concept Nodes */}
                {dagLayout.placedNodes.map((pn) => {
                  const { node, x, y, width, height } = pn;
                  const styles = getConceptNodeStyles(node.status);
                  const isSelected = selectedConceptNode?.id === node.id;

                  return (
                    <g
                      key={node.id}
                      transform={`translate(${x}, ${y})`}
                      role="button"
                      tabIndex={0}
                      aria-label={`${node.name} (Nivel ${node.depth_level})`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedConceptNode(node);
                        setSelectedNode(null);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          e.stopPropagation();
                          setSelectedConceptNode(node);
                          setSelectedNode(null);
                        }
                      }}
                      className="cursor-pointer group focus:outline-none"
                    >
                      <rect
                        width={width}
                        height={height}
                        rx="12"
                        className={`${styles.bg} transition-all duration-150 group-hover:stroke-indigo-400 group-hover:filter group-hover:drop-shadow-[0_0_12px_rgba(99,102,241,0.5)] ${
                          isSelected ? 'stroke-2 ring-2 ring-indigo-400 stroke-indigo-400' : 'stroke'
                        }`}
                      />
                      <foreignObject width={width} height={height}>
                        <div className="flex h-full w-full flex-col justify-between p-2.5 text-left select-none">
                          <div className="flex items-center justify-between gap-1">
                            <span className="font-mono text-[10px] text-indigo-400 font-bold uppercase tracking-wider">
                              Nivel {node.depth_level}
                            </span>
                            <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase border ${styles.badgeBg}`}>
                              {styles.badgeLabel}
                            </span>
                          </div>
                          <p className={`text-xs font-bold truncate ${styles.textColor}`} title={node.name}>
                            {node.name}
                          </p>
                          <div className="flex items-center justify-between text-[10px] text-slate-400">
                            <span className="truncate max-w-[120px] font-mono text-[9px]">
                              {node.taxonomy_path || 'general'}
                            </span>
                            <span className="font-semibold text-slate-300">
                              {node.card_count} {node.card_count === 1 ? 'tarjeta' : 'tarjetas'}
                            </span>
                          </div>
                        </div>
                      </foreignObject>
                    </g>
                  );
                })}
              </>
            ) : (
              <>
                {/* Fallback to Cluster Tree if DAG not yet extracted */}
                {layout.edges.map((edge, idx) => {
                  const dy = edge.targetY - edge.sourceY;
                  const controlY1 = edge.sourceY + dy * 0.45;
                  const controlY2 = edge.targetY - dy * 0.45;
                  const pathD = `M ${edge.sourceX} ${edge.sourceY} C ${edge.sourceX} ${controlY1}, ${edge.targetX} ${controlY2}, ${edge.targetX} ${edge.targetY}`;

                  const strokeColor =
                    edge.health === 'gap'
                      ? 'rgba(244, 63, 94, 0.45)'
                      : edge.health === 'bad' || edge.health === 'broken' || edge.health === 'debt'
                      ? 'rgba(244, 63, 94, 0.55)'
                      : edge.health === 'unreviewed'
                      ? 'rgba(100, 116, 139, 0.35)'
                      : 'rgba(16, 185, 129, 0.45)';

                  return (
                    <path
                      key={`edge-${idx}`}
                      d={pathD}
                      fill="none"
                      stroke={strokeColor}
                      strokeWidth="1.5"
                      strokeDasharray={edge.health === 'gap' ? '4,4' : undefined}
                      markerEnd="url(#arrowhead)"
                    />
                  );
                })}

                {/* Render Nodes */}
                {layout.placedNodes.map((pn) => {
                  const { node, x, y, width, height } = pn;
                  const styles = getNodeStyles(node);
                  const isSelected = selectedNode?.id === node.id;
                  const cleanTarget = targetConcept?.toLowerCase().trim();
                  const lbl = node.label.toLowerCase().trim();
                  const det = (node.details || '').toLowerCase().trim();
                  const id = node.id.toLowerCase().trim();
                  const isTargeted = Boolean(
                    cleanTarget &&
                      ((lbl.length >= 3 && (lbl.includes(cleanTarget) || cleanTarget.includes(lbl))) ||
                        (det.length >= 4 && (det.includes(cleanTarget) || cleanTarget.includes(det))) ||
                        id.includes(cleanTarget))
                  );

                  return (
                    <g
                      key={node.id}
                      transform={`translate(${x}, ${y})`}
                      role="button"
                      tabIndex={0}
                      aria-label={`${node.label}${node.note_id ? ` (Nota #${node.note_id})` : ''}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedNode(node);
                        setSelectedConceptNode(null);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          e.stopPropagation();
                          setSelectedNode(node);
                          setSelectedConceptNode(null);
                        }
                      }}
                      className="cursor-pointer group focus:outline-none focus-visible:outline-indigo-500"
                    >
                      <rect
                        width={width}
                        height={height}
                        rx="10"
                        className={`${styles.bg} transition-all duration-150 group-hover:stroke-indigo-400 group-hover:filter group-hover:drop-shadow-[0_0_8px_rgba(99,102,241,0.5)] ${
                          isTargeted
                            ? 'stroke-2 ring-4 ring-rose-500 stroke-rose-400 filter drop-shadow-[0_0_16px_rgba(244,63,94,0.9)] animate-pulse'
                            : isSelected
                            ? 'stroke-2 ring-2 ring-indigo-400 stroke-indigo-400'
                            : styles.strokeWidth
                        }`}
                        strokeDasharray={node.health === 'gap' ? '4,4' : undefined}
                      />
                      <foreignObject width={width} height={height}>
                        <div className="relative flex h-full w-full items-center justify-between px-3 py-1.5 text-left">
                          <div className="flex items-center gap-2 min-w-0">
                            {node.type === 'deck' && <Layers className="h-4 w-4 text-indigo-400 shrink-0" />}
                            {node.type === 'cluster' && <Folder className="h-3.5 w-3.5 text-slate-400 shrink-0" />}
                            {node.type === 'note' && node.health === 'optimal' && (
                              <ShieldCheck className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                            )}
                            {node.type === 'note' &&
                              (node.health === 'bad' || node.health === 'debt' || node.health === 'broken') && (
                                <AlertTriangle className="h-3.5 w-3.5 text-rose-400 shrink-0" />
                              )}
                            {node.type === 'note' && node.health === 'unreviewed' && (
                              <HelpCircle className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                            )}
                            {node.type === 'gap' && <AlertCircle className="h-3.5 w-3.5 text-rose-400 shrink-0" />}

                            <div className="min-w-0">
                              <p className={`text-xs font-semibold truncate ${styles.textColor}`} title={node.label}>
                                {node.label}
                              </p>
                              {node.note_id && (
                                <span className="font-mono text-[9px] text-slate-400">#{node.note_id}</span>
                              )}
                            </div>
                          </div>

                          <span
                            className={`ml-1 shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase border ${styles.badgeBg}`}
                          >
                            {node.type === 'deck'
                              ? 'Mazo'
                              : node.type === 'cluster'
                              ? 'Eje'
                              : node.health === 'gap'
                              ? 'Brecha'
                              : node.health === 'bad' || node.health === 'debt' || node.health === 'broken'
                              ? 'Mala'
                              : node.health === 'unreviewed'
                              ? 'Sin Evaluar'
                              : 'Óptima'}
                          </span>
                        </div>
                      </foreignObject>
                    </g>
                  );
                })}
              </>
            )}
          </g>
        </svg>

        {/* Zoom Controls Overlay */}
        <div className="absolute bottom-4 right-4 flex items-center gap-1 rounded-xl border border-slate-700 bg-slate-900/90 p-1 backdrop-blur-md shadow-lg">
          <button
            type="button"
            onClick={() => setZoom((z) => Math.min(2.0, z + 0.15))}
            aria-label="Acercar vista del grafo"
            className="p-1.5 rounded-lg text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
            title="Acercar (+)"
          >
            <ZoomIn className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setZoom((z) => Math.max(0.4, z - 0.15))}
            aria-label="Alejar vista del grafo"
            className="p-1.5 rounded-lg text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
            title="Alejar (-)"
          >
            <ZoomOut className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={handleResetZoom}
            aria-label="Reiniciar zoom del grafo"
            className="p-1.5 rounded-lg text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
            title="Reiniciar vista"
          >
            <RotateCcw className="h-4 w-4" />
          </button>
          <span className="px-2 text-[10px] font-mono text-slate-400">
            {Math.round(zoom * 100)}%
          </span>
        </div>

        {/* Selected Concept Node Details Drawer (G-08, G-09) */}
        {selectedConceptNode && (
          <div className="absolute top-4 right-4 z-30 w-80 max-w-[calc(100%-2rem)] rounded-2xl border border-slate-700 bg-slate-900/95 p-4 shadow-2xl backdrop-blur-md text-slate-100 animate-fade-in space-y-3">
            <div className="flex items-start justify-between gap-2 border-b border-slate-800 pb-2.5">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="rounded bg-indigo-500/20 px-1.5 py-0.5 font-mono text-[10px] font-bold text-indigo-300">
                    Nivel {selectedConceptNode.depth_level}
                  </span>
                  <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-400 uppercase">
                    {selectedConceptNode.status || 'RAW'}
                  </span>
                </div>
                <h4 className="text-sm font-bold text-white break-words" title={selectedConceptNode.name}>
                  {selectedConceptNode.name}
                </h4>
                <p className="font-mono text-[10px] text-slate-400 truncate">
                  {selectedConceptNode.taxonomy_path || 'general'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedConceptNode(null)}
                aria-label="Cerrar panel de detalle del concepto"
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Metrics */}
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div className="rounded-lg bg-slate-950/60 p-2 border border-slate-800/80">
                <span className="text-slate-400 block text-[10px]">Grados In / Out</span>
                <span className="font-bold text-white font-mono">
                  {selectedConceptNode.in_degree ?? 0} / {selectedConceptNode.out_degree ?? 0}
                </span>
              </div>
              <div className="rounded-lg bg-slate-950/60 p-2 border border-slate-800/80">
                <span className="text-slate-400 block text-[10px]">Tarjetas</span>
                <span className="font-bold text-white font-mono">
                  {selectedConceptNode.card_count} notas
                </span>
              </div>
            </div>

            {/* Socratic Red-Teaming Challenge Button (G-09: Validated status & canonical ID) */}
            {(() => {
              const canLaunchSocratic =
                selectedConceptNode.status === 'SANITIZED' ||
                selectedConceptNode.status === 'SUFFICIENT' ||
                selectedConceptNode.status === 'MASTERED';

              return (
                <div className="space-y-1">
                  <button
                    type="button"
                    disabled={!canLaunchSocratic}
                    onClick={() => {
                      if (canLaunchSocratic) {
                        setSocraticConceptName(selectedConceptNode.id);
                        setIsSocraticModalOpen(true);
                      }
                    }}
                    className={`w-full inline-flex items-center justify-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-bold transition-all shadow-sm ${
                      canLaunchSocratic
                        ? 'border-amber-500/40 bg-amber-950/40 hover:bg-amber-900/60 text-amber-300 hover:text-white cursor-pointer active:scale-95 shadow-amber-500/10'
                        : 'border-slate-800 bg-slate-900/40 text-slate-500 cursor-not-allowed opacity-60'
                    }`}
                    title={
                      canLaunchSocratic
                        ? 'Poner a prueba tu modelo mental frente a un caso adverso (Red-Teaming)'
                        : 'El concepto requiere estar saneado o evaluado para habilitar el reto socrático'
                    }
                  >
                    <Sparkles className="h-3.5 w-3.5 text-amber-400" />
                    <span>🎯 Reto Socrático de Maestría</span>
                  </button>
                  {!canLaunchSocratic && (
                    <p className="text-[10px] text-amber-400/80 italic text-center">
                      ⚠️ Sanea las tarjetas de este concepto para activar el Reto Socrático.
                    </p>
                  )}
                </div>
              );
            })()}

            {/* Mapped Flashcards List */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs font-bold text-slate-300">
                <span>Tarjetas del Concepto ({conceptMappedCards.length})</span>
              </div>

              {conceptMappedCards.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-800 p-3 text-center text-xs text-slate-500">
                  No hay tarjetas indexadas directamente para este concepto.
                </div>
              ) : (
                <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                  {conceptMappedCards.map((cardNode) => (
                    <div
                      key={cardNode.id}
                      className="rounded-xl border border-slate-800 bg-slate-950/60 p-2.5 space-y-1.5 text-xs"
                    >
                      <div className="flex items-start justify-between gap-1">
                        <p className="font-semibold text-slate-200 line-clamp-2">
                          {cardNode.label}
                        </p>
                        {cardNode.note_id && (
                          <span className="font-mono text-[9px] text-slate-400 shrink-0">
                            #{cardNode.note_id}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2 pt-1 border-t border-slate-800/60">
                        {cardNode.note_id && onInspectNote && (
                          <button
                            type="button"
                            onClick={() => onInspectNote(cardNode.note_id!, cardNode.label)}
                            className="inline-flex items-center gap-1 text-[10px] font-bold text-indigo-400 hover:text-indigo-300 cursor-pointer"
                          >
                            <Search className="h-3 w-3" />
                            <span>Planificar</span>
                          </button>
                        )}
                        {cardNode.note_id && onEnqueueNote && (
                          <button
                            type="button"
                            onClick={() => onEnqueueNote(cardNode.note_id!, cardNode.label)}
                            className="inline-flex items-center gap-1 text-[10px] font-bold text-slate-400 hover:text-slate-200 cursor-pointer"
                          >
                            <BookmarkPlus className="h-3 w-3" />
                            <span>Encolar</span>
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Selected Node Details Drawer */}
        {selectedNode && (
          <div className="absolute top-4 right-4 z-30 w-80 max-w-[calc(100%-2rem)] rounded-2xl border border-slate-700 bg-slate-900/95 p-4 shadow-2xl backdrop-blur-md text-slate-100 animate-fade-in space-y-3">
            <div className="flex items-start justify-between gap-2 border-b border-slate-800 pb-2.5">
              <div className="flex items-center gap-2">
                {selectedNode.type === 'deck' && (
                  <Layers className="h-4 w-4 text-indigo-400" />
                )}
                {selectedNode.type === 'cluster' && (
                  <Folder className="h-4 w-4 text-slate-400" />
                )}
                {selectedNode.health === 'optimal' && (
                  <ShieldCheck className="h-4 w-4 text-emerald-400" />
                )}
                {(selectedNode.health === 'bad' || selectedNode.health === 'debt' || selectedNode.health === 'broken') && (
                  <AlertTriangle className="h-4 w-4 text-rose-400" />
                )}
                {selectedNode.health === 'unreviewed' && (
                  <HelpCircle className="h-4 w-4 text-slate-400" />
                )}
                {selectedNode.health === 'gap' && (
                  <AlertCircle className="h-4 w-4 text-rose-400" />
                )}
                <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
                  {selectedNode.type === 'deck'
                    ? 'Mazo Principal'
                    : selectedNode.type === 'cluster'
                    ? 'Eje Temático'
                    : selectedNode.health === 'gap'
                    ? 'Brecha Huérfana'
                    : selectedNode.health === 'bad' || selectedNode.health === 'debt' || selectedNode.health === 'broken'
                    ? 'Tarjeta Mala'
                    : selectedNode.health === 'unreviewed'
                    ? 'Tarjeta Sin Evaluar'
                    : 'Tarjeta Atómica Óptima'}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setSelectedNode(null)}
                aria-label="Cerrar panel de detalle del nodo"
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-2">
              <h4 className="text-sm font-bold text-white break-words">
                {selectedNode.label}
              </h4>

              <div className="flex items-center gap-2 flex-wrap">
                {selectedNode.note_id && (
                  <div className="flex items-center gap-1.5 font-mono text-[11px] text-indigo-300 bg-slate-950/80 px-2 py-1 rounded border border-slate-800">
                    <span>Nota ID: #{selectedNode.note_id}</span>
                  </div>
                )}
                {selectedNode.quality_score !== undefined && selectedNode.quality_score !== null && (
                  <div className="flex items-center gap-1 text-[11px] font-semibold text-emerald-300 bg-emerald-950/40 px-2 py-1 rounded border border-emerald-800/40">
                    <span>Calidad: {Math.round(selectedNode.quality_score * 100)}%</span>
                  </div>
                )}
              </div>

              {selectedNode.details && (
                <div className="rounded-lg bg-slate-950/70 p-2.5 text-xs text-slate-300 border border-slate-800/80 whitespace-pre-wrap max-h-36 overflow-y-auto">
                  {selectedNode.details}
                </div>
              )}

              {selectedNode.quality_feedback && (
                <div className="rounded-lg bg-indigo-950/40 p-2.5 text-xs text-indigo-200 border border-indigo-800/50 space-y-1">
                  <div className="flex items-center gap-1 font-bold text-[10px] uppercase text-indigo-400">
                    <Sparkles className="h-3 w-3" />
                    <span>Diagnóstico Cognitivo IA</span>
                  </div>
                  <p className="text-[11px] leading-relaxed italic text-indigo-200/90">
                    {selectedNode.quality_feedback}
                  </p>
                </div>
              )}
            </div>

            {/* Actions in drawer */}
            <div className="pt-2 border-t border-slate-800 flex flex-col gap-2">
              {/* Socratic Red-Teaming Challenge Button */}
              {selectedNode && (
                <button
                  type="button"
                  onClick={() => {
                    setSocraticConceptName(selectedNode.label);
                    setIsSocraticModalOpen(true);
                  }}
                  className="w-full inline-flex items-center justify-center gap-1.5 rounded-xl border border-amber-500/40 bg-amber-950/40 hover:bg-amber-900/60 px-3 py-2 text-xs font-bold text-amber-300 hover:text-white transition-all active:scale-95 cursor-pointer shadow-sm shadow-amber-500/10"
                  title="Poner a prueba tu modelo mental frente a un caso adverso (Red-Teaming)"
                >
                  <Sparkles className="h-3.5 w-3.5 text-amber-400" />
                  <span>🎯 Reto Socrático de Maestría</span>
                </button>
              )}

              {selectedNode.note_id && onInspectNote && (
                <button
                  type="button"
                  onClick={() => onInspectNote(selectedNode.note_id!, selectedNode.label)}
                  className="w-full inline-flex items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 px-3 py-2 text-xs font-bold text-white shadow-md shadow-indigo-600/20 transition-all active:scale-95 cursor-pointer"
                  title="Descomponer esta tarjeta mediante Diagnóstico y Planificación"
                >
                  <Search className="h-3.5 w-3.5" />
                  <span>🔍 Analizar y Planificar</span>
                </button>
              )}

              {selectedNode.note_id && onEnqueueNote && (
                <button
                  type="button"
                  onClick={() => onEnqueueNote(selectedNode.note_id!, selectedNode.label)}
                  className="w-full inline-flex items-center justify-center gap-1.5 rounded-xl border border-indigo-500/40 bg-indigo-950/60 hover:bg-indigo-900/80 px-3 py-1.5 text-xs font-semibold text-indigo-300 hover:text-white transition-all active:scale-95 cursor-pointer"
                  title="Reservar en la cola de curación para trabajar luego"
                >
                  <BookmarkPlus className="h-3.5 w-3.5 text-indigo-400" />
                  <span>📌 Encolar para Curación</span>
                </button>
              )}

              {selectedNode.health === 'gap' && onEnqueueGap && (
                <button
                  type="button"
                  onClick={() =>
                    onEnqueueGap(
                      selectedNode.label,
                      selectedNode.details || 'Brecha temática detectada en DAG'
                    )
                  }
                  className="w-full inline-flex items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-2 text-xs font-bold text-white shadow-md shadow-indigo-600/20 hover:from-indigo-500 hover:to-violet-500 transition-all active:scale-95 cursor-pointer"
                >
                  <BookmarkPlus className="h-3.5 w-3.5" />
                  <span>Encolar en Curación</span>
                </button>
              )}
            </div>
          </div>
        )}
      </div>
      ) : (
        <div className="flex-1 w-full overflow-y-auto p-4 sm:p-6 bg-slate-950/60 space-y-4">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center p-12 space-y-3 text-slate-400">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
              <p className="text-xs font-semibold">Cargando inventario de tarjetas y brechas...</p>
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-12 text-center rounded-2xl border border-slate-800 bg-slate-900/40 space-y-3">
              <HelpCircle className="h-10 w-10 text-slate-400" />
              <p className="text-sm font-bold text-slate-300">No se encontraron elementos</p>
              <p className="text-xs text-slate-400 max-w-sm">
                No hay tarjetas ni brechas que coincidan con el filtro '{filter}' o el término de búsqueda '{searchQuery}'.
              </p>
              <button
                type="button"
                onClick={() => {
                  setFilter('all');
                  setSearchQuery('');
                }}
                className="mt-2 rounded-xl bg-slate-800 hover:bg-slate-700 px-3.5 py-1.5 text-xs font-semibold text-slate-300 cursor-pointer transition-colors"
              >
                Limpiar filtros
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Accordion Controls Bar */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-slate-400 px-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span>
                    Mostrando <strong className="text-white">{filteredItems.length}</strong> elementos en{' '}
                    <strong className="text-indigo-300">{groupedThemes.length}</strong> ejes temáticos de '{deckName}'
                  </span>
                  <span className="text-[10px] font-mono uppercase bg-slate-900 px-2 py-0.5 rounded border border-slate-800 text-slate-400">
                    Filtro: {filter}
                  </span>
                </div>

                <div className="flex items-center gap-2 self-start sm:self-auto">
                  <button
                    type="button"
                    onClick={expandAllClusters}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-900/80 px-2.5 py-1 text-[11px] font-semibold text-slate-300 hover:bg-slate-800 hover:text-white transition-colors cursor-pointer"
                    title="Desplegar todos los ejes temáticos"
                  >
                    <ChevronsDown className="h-3.5 w-3.5 text-indigo-400" />
                    <span>Expandir Todos</span>
                  </button>
                  <button
                    type="button"
                    onClick={collapseAllClusters}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-900/80 px-2.5 py-1 text-[11px] font-semibold text-slate-300 hover:bg-slate-800 hover:text-white transition-colors cursor-pointer"
                    title="Plegar todos los ejes temáticos"
                  >
                    <ChevronsUp className="h-3.5 w-3.5 text-slate-400" />
                    <span>Colapsar Todos</span>
                  </button>
                </div>
              </div>

              {/* Accordion Themes List */}
              <div className="space-y-3">
                {groupedThemes.map((group) => {
                  const isCollapsed = !!collapsedClusters[group.clusterId];

                  return (
                    <div
                      key={group.clusterId}
                      className="rounded-2xl border border-slate-800/90 bg-slate-900/60 overflow-hidden shadow-md transition-all"
                    >
                      {/* Theme Accordion Header */}
                      <button
                        type="button"
                        onClick={() => toggleCluster(group.clusterId)}
                        className="w-full flex items-center justify-between p-3.5 sm:px-4 text-left hover:bg-surface-elevated/80 transition-colors cursor-pointer select-none"
                      >
                        <div className="flex items-center gap-2.5 min-w-0 pr-2">
                          <div className="p-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 shrink-0">
                            {isCollapsed ? (
                              <Folder className="h-4 w-4" />
                            ) : (
                              <FolderOpen className="h-4 w-4" />
                            )}
                          </div>
                          <span className="text-sm font-bold text-slate-100 truncate">
                            {group.clusterLabel}
                          </span>
                          <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-mono font-bold text-slate-300 shrink-0">
                            {group.items.length}
                          </span>
                        </div>

                        {/* Right: Metrics Pills & Chevron */}
                        <div className="flex items-center gap-2 shrink-0">
                          {group.badCount > 0 && (
                            <span className="hidden sm:inline-flex items-center gap-1 rounded-full bg-rose-500/15 border border-rose-500/30 px-2 py-0.5 text-[10px] font-bold text-rose-300">
                              <AlertTriangle className="h-3 w-3 text-rose-400" />
                              {group.badCount} Por Sanear
                            </span>
                          )}
                          {group.gapCount > 0 && (
                            <span className="hidden sm:inline-flex items-center gap-1 rounded-full bg-amber-500/15 border border-amber-500/30 px-2 py-0.5 text-[10px] font-bold text-amber-300">
                              <AlertCircle className="h-3 w-3 text-amber-400" />
                              {group.gapCount} Brechas
                            </span>
                          )}
                          {group.optimalCount > 0 && (
                            <span className="hidden md:inline-flex items-center gap-1 rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-bold text-emerald-300">
                              <ShieldCheck className="h-3 w-3 text-emerald-400" />
                              {group.optimalCount} Óptimas
                            </span>
                          )}
                          {group.unreviewedCount > 0 && (
                            <span className="hidden lg:inline-flex items-center gap-1 rounded-full bg-slate-800 border border-slate-700 px-2 py-0.5 text-[10px] font-bold text-slate-400">
                              <HelpCircle className="h-3 w-3 text-slate-400" />
                              {group.unreviewedCount} Sin Evaluar
                            </span>
                          )}

                          <ChevronDown
                            className={`h-4 w-4 text-slate-400 transition-transform duration-200 ${
                              isCollapsed ? '-rotate-90' : 'rotate-0 text-indigo-400'
                            }`}
                          />
                        </div>
                      </button>

                      {/* Theme Accordion Items Content */}
                      {!isCollapsed && (
                        <div className="border-t border-slate-800/80 p-3.5 sm:p-4 space-y-3 bg-slate-950/40">
                          {group.items.map((item) => {
                            const isGap = item.type === 'gap' || item.health === 'gap';

                            if (isGap) {
                              return (
                                <div
                                  key={item.id}
                                  className="rounded-xl border border-dashed border-rose-500/40 bg-rose-950/20 p-3.5 hover:border-rose-500/60 transition-all shadow-xs"
                                >
                                  <div className="flex flex-col md:flex-row md:items-start justify-between gap-3">
                                    <div className="flex-1 space-y-1.5 min-w-0">
                                      <div className="flex items-center gap-2 flex-wrap">
                                        <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/40 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider">
                                          <AlertCircle className="h-3 w-3 text-rose-400" />
                                          Brecha Huérfana
                                        </span>
                                        <span className="text-[11px] font-mono text-slate-400">
                                          {item.id}
                                        </span>
                                      </div>

                                      <h4 className="text-sm font-semibold text-rose-100 break-words leading-snug">
                                        {item.label}
                                      </h4>

                                      {item.details && (
                                        <p className="text-xs text-rose-200/80 line-clamp-2 break-words bg-rose-950/30 p-2 rounded-lg border border-rose-900/40 font-sans whitespace-pre-wrap">
                                          {item.details}
                                        </p>
                                      )}
                                    </div>

                                    <div className="shrink-0 pt-1 md:pt-0">
                                      {onEnqueueGap && (
                                        <button
                                          type="button"
                                          onClick={() =>
                                            onEnqueueGap(
                                              item.label,
                                              item.details || 'Brecha temática detectada en DAG'
                                            )
                                          }
                                          className="w-full md:w-auto inline-flex items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-rose-600 to-amber-600 hover:from-rose-500 hover:to-amber-500 px-3 py-1.5 text-xs font-bold text-white shadow-md shadow-rose-900/30 active:scale-95 transition-all cursor-pointer whitespace-nowrap"
                                          title="Encolar esta brecha huérfana para expandir con IA en Fase 4"
                                        >
                                          <BookmarkPlus className="h-3.5 w-3.5" />
                                          <span>Encolar para Expansión</span>
                                        </button>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              );
                            }

                            // Note Item
                            const isOptimal = item.health === 'optimal';
                            const isBad = item.health === 'bad' || item.health === 'debt' || item.health === 'broken';
                            const isUnreviewed = item.health === 'unreviewed';

                            return (
                              <div
                                key={item.id}
                                className={`rounded-xl border p-3.5 transition-all duration-150 shadow-xs ${
                                  isOptimal
                                    ? 'border-emerald-500/30 bg-emerald-950/20 hover:border-emerald-500/50'
                                    : isBad
                                    ? 'border-rose-500/30 bg-rose-950/20 hover:border-rose-500/50'
                                    : 'border-slate-800 bg-slate-900/60 hover:border-slate-700'
                                }`}
                              >
                                <div className="flex flex-col md:flex-row md:items-start justify-between gap-3">
                                  {/* Left: Card Details */}
                                  <div className="flex-1 space-y-2 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                      {item.note_id && (
                                        <span className="font-mono text-xs font-bold text-slate-400 bg-slate-950/80 px-2 py-0.5 rounded-md border border-slate-800">
                                          #{item.note_id}
                                        </span>
                                      )}

                                      {/* Status Badge */}
                                      {isOptimal && (
                                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider">
                                          <ShieldCheck className="h-3 w-3 text-emerald-400" />
                                          Óptima
                                        </span>
                                      )}
                                      {isUnreviewed && (
                                        <span className="inline-flex items-center gap-1 rounded-full bg-slate-800 text-slate-400 border border-slate-700 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider">
                                          <HelpCircle className="h-3 w-3 text-slate-400" />
                                          Sin Evaluar
                                        </span>
                                      )}
                                      {isBad && (
                                        <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/40 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider">
                                          <AlertTriangle className="h-3 w-3 text-rose-400" />
                                          Mala
                                        </span>
                                      )}

                                      {item.quality_score !== undefined && item.quality_score !== null && (
                                        <span className="text-[10px] font-bold text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
                                          Calidad: {Math.round(item.quality_score * 100)}%
                                        </span>
                                      )}
                                    </div>

                                    {/* Front Preview */}
                                    <h4 className="text-sm font-semibold text-slate-100 break-words leading-snug">
                                      {item.label}
                                    </h4>

                                    {/* Back Preview if details exist */}
                                    {item.details && (
                                      <p className="text-xs text-slate-400 line-clamp-2 break-words bg-slate-950/50 p-2 rounded-lg border border-slate-800/60 font-sans whitespace-pre-wrap">
                                        {item.details}
                                      </p>
                                    )}

                                    {/* AI Diagnostic feedback if present */}
                                    {item.quality_feedback && (
                                      <div className="flex items-start gap-1.5 text-xs text-indigo-300/90 bg-indigo-950/30 border border-indigo-900/40 rounded-lg p-2">
                                        <Sparkles className="h-3.5 w-3.5 text-indigo-400 shrink-0 mt-0.5" />
                                        <span className="italic">{item.quality_feedback}</span>
                                      </div>
                                    )}
                                  </div>

                                  {/* Right: Action Buttons */}
                                  <div className="flex md:flex-col items-stretch gap-2 shrink-0 pt-2 md:pt-0 min-w-[180px]">
                                    {item.note_id && onInspectNote && (
                                      <button
                                        type="button"
                                        onClick={() => onInspectNote(item.note_id!, item.label)}
                                        className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 px-3 py-1.5 text-xs font-bold text-white shadow-md shadow-indigo-600/20 active:scale-95 transition-all cursor-pointer whitespace-nowrap"
                                        title="Analizar y planificar descomposición de la tarjeta"
                                      >
                                        <Search className="h-3.5 w-3.5" />
                                        <span>Analizar & Planificar</span>
                                      </button>
                                    )}

                                    {item.note_id && onEnqueueNote && (
                                      <button
                                        type="button"
                                        onClick={() => onEnqueueNote(item.note_id!, item.label)}
                                        className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-indigo-500/40 bg-indigo-950/60 hover:bg-indigo-900/80 px-3 py-1.5 text-xs font-semibold text-indigo-300 hover:text-white active:scale-95 transition-all cursor-pointer whitespace-nowrap"
                                        title="Reservar en cola de curación para resolver luego"
                                      >
                                        <BookmarkPlus className="h-3.5 w-3.5 text-indigo-400" />
                                        <span>Encolar para Curación</span>
                                      </button>
                                    )}
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Socratic Red-Teaming Challenge Modal */}
      {isSocraticModalOpen && (
        <SocraticNodeMasteryModal
          isOpen={isSocraticModalOpen}
          onClose={() => setIsSocraticModalOpen(false)}
          deckName={deckName}
          conceptName={socraticConceptName}
          apiKey={apiKey}
          onMasteryAchieved={(_concept) => {
            fetchCoverageMap();
          }}
        />
      )}

      {/* Pedagogical Order Audit Modal */}
      {isAuditModalOpen && (
        <PedagogicalOrderAuditModal
          isOpen={isAuditModalOpen}
          onClose={() => setIsAuditModalOpen(false)}
          deckName={deckName}
          onAligned={() => {
            fetchCoverageMap();
          }}
        />
      )}
    </div>
  );
};

