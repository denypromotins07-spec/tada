"""
Fundamentals Graph - In-memory NetworkX graph for crypto market cycles
and cross-chain ecosystems (Domain 14).

Maps relationships between:
- Layer 1 blockchains
- Layer 2 solutions
- DeFi protocols
- Token ecosystems
- Cross-chain bridges
"""

import networkx as nx
from typing import Dict, List, Optional, Any, Set
from datetime import datetime


class FundamentalsGraph:
    """
    In-memory knowledge graph mapping crypto market fundamentals.
    Used by Market Data Agent for ecosystem analysis.
    """

    def __init__(self):
        self.graph = nx.DiGraph()
        self.last_updated = datetime.utcnow()
        self._initialize_base_ecosystem()

    def _initialize_base_ecosystem(self):
        """Initialize with base crypto ecosystem structure"""
        
        # Layer 1 blockchains
        l1_nodes = [
            ("ethereum", {"type": "layer1", "category": "smart_contract", "tvl_rank": 1}),
            ("bitcoin", {"type": "layer1", "category": "store_of_value", "tvl_rank": None}),
            ("solana", {"type": "layer1", "category": "smart_contract", "tvl_rank": 5}),
            ("cardano", {"type": "layer1", "category": "smart_contract", "tvl_rank": 10}),
            ("avalanche", {"type": "layer1", "category": "smart_contract", "tvl_rank": 8}),
            ("polkadot", {"type": "layer1", "category": "interoperability", "tvl_rank": 12}),
            ("cosmos", {"type": "layer1", "category": "interoperability", "tvl_rank": 15}),
            ("near", {"type": "layer1", "category": "smart_contract", "tvl_rank": 18}),
        ]
        
        for node, attrs in l1_nodes:
            self.graph.add_node(node, **attrs)
        
        # Layer 2 solutions
        l2_nodes = [
            ("arbitrum", {"type": "layer2", "parent": "ethereum", "category": "optimistic_rollup"}),
            ("optimism", {"type": "layer2", "parent": "ethereum", "category": "optimistic_rollup"}),
            ("polygon_zkevm", {"type": "layer2", "parent": "ethereum", "category": "zkevm"}),
            ("starknet", {"type": "layer2", "parent": "ethereum", "category": "zk_stark"}),
            ("base", {"type": "layer2", "parent": "ethereum", "category": "optimistic_rollup"}),
        ]
        
        for node, attrs in l2_nodes:
            self.graph.add_node(node, **attrs)
            if "parent" in attrs:
                self.graph.add_edge(attrs["parent"], node, relationship="scales_to")
        
        # Major DeFi protocols
        defi_protocols = [
            ("uniswap", {"type": "protocol", "category": "dex", "chains": ["ethereum", "arbitrum", "optimism", "polygon"]}),
            ("aave", {"type": "protocol", "category": "lending", "chains": ["ethereum", "arbitrum", "optimism", "avalanche"]}),
            ("compound", {"type": "protocol", "category": "lending", "chains": ["ethereum", "arbitrum", "base"]}),
            ("curve", {"type": "protocol", "category": "dex_stableswap", "chains": ["ethereum", "arbitrum", "optimism"]}),
            ("makerdao", {"type": "protocol", "category": "cdp", "chains": ["ethereum"]}),
            ("lido", {"type": "protocol", "category": "liquid_staking", "chains": ["ethereum", "solana", "polygon"]}),
        ]
        
        for node, attrs in defi_protocols:
            self.graph.add_node(node, **attrs)
            for chain in attrs.get("chains", []):
                if self.graph.has_node(chain):
                    self.graph.add_edge(chain, node, relationship="deployed_on")
        
        # Cross-chain bridges
        bridges = [
            ("stargate", {"type": "bridge", "connected_chains": ["ethereum", "arbitrum", "optimism", "avalanche", "polygon"]}),
            ("hop_protocol", {"type": "bridge", "connected_chains": ["ethereum", "arbitrum", "optimism", "polygon"]}),
            ("wormhole", {"type": "bridge", "connected_chains": ["ethereum", "solana", "avalanche", "polygon"]}),
        ]
        
        for node, attrs in bridges:
            self.graph.add_node(node, **attrs)
            for chain in attrs.get("connected_chains", []):
                if self.graph.has_node(chain):
                    self.graph.add_edge(chain, node, relationship="bridged_by")
                    self.graph.add_edge(node, chain, relationship="bridges_to")
        
        # Stablecoin relationships
        stablecoins = {
            "usdt": {"issuer": "tether", "chains": ["ethereum", "tron", "solana", "avalanche", "polygon"]},
            "usdc": {"issuer": "circle", "chains": ["ethereum", "solana", "avalanche", "polygon", "base"]},
            "dai": {"issuer": "makerdao", "chains": ["ethereum", "arbitrum", "optimism", "polygon"]},
        }
        
        for symbol, attrs in stablecoins.items():
            self.graph.add_node(symbol, type="stablecoin", **attrs)
            for chain in attrs.get("chains", []):
                if self.graph.has_node(chain):
                    self.graph.add_edge(chain, symbol, relationship="supports")

    def get_ecosystem_for_chain(self, chain: str) -> Dict[str, List[str]]:
        """Get all related entities for a given chain"""
        if not self.graph.has_node(chain):
            return {}
        
        ecosystem = {
            "layer2s": [],
            "protocols": [],
            "bridges": [],
            "stablecoins": [],
        }
        
        # Get successors (things built on this chain)
        for successor in self.graph.successors(chain):
            node_type = self.graph.nodes[successor].get("type")
            if node_type == "layer2":
                ecosystem["layer2s"].append(successor)
            elif node_type == "protocol":
                ecosystem["protocols"].append(successor)
            elif node_type == "bridge":
                ecosystem["bridges"].append(successor)
            elif node_type == "stablecoin":
                ecosystem["stablecoins"].append(successor)
        
        return ecosystem

    def find_paths_between_chains(self, source: str, target: str) -> List[List[str]]:
        """Find all paths between two chains (for cross-chain routing)"""
        if not self.graph.has_node(source) or not self.graph.has_node(target):
            return []
        
        try:
            paths = list(nx.all_simple_paths(self.graph, source, target, cutoff=4))
            return paths
        except nx.NetworkXNoPath:
            return []

    def get_connected_components(self) -> int:
        """Get number of connected components in the ecosystem"""
        undirected = self.graph.to_undirected()
        return nx.number_connected_components(undirected)

    def get_central_chains(self, top_n: int = 5) -> List[str]:
        """Get most central chains by degree centrality"""
        centrality = nx.degree_centrality(self.graph)
        sorted_chains = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
        return [chain for chain, _ in sorted_chains[:top_n]]

    def add_custom_relationship(self, source: str, target: str, relationship: str):
        """Add a custom relationship between nodes"""
        if self.graph.has_node(source) and self.graph.has_node(target):
            self.graph.add_edge(source, target, relationship=relationship)

    def get_node_info(self, node: str) -> Optional[Dict]:
        """Get all attributes for a node"""
        if self.graph.has_node(node):
            return dict(self.graph.nodes[node])
        return None

    def get_neighbors(self, node: str, relationship: Optional[str] = None) -> List[str]:
        """Get neighbors of a node, optionally filtered by relationship type"""
        if not self.graph.has_node(node):
            return []
        
        neighbors = []
        for neighbor in self.graph.neighbors(node):
            if relationship is None:
                neighbors.append(neighbor)
            else:
                edge_data = self.graph.get_edge_data(node, neighbor)
                if edge_data and edge_data.get("relationship") == relationship:
                    neighbors.append(neighbor)
        
        return neighbors

    def export_graph_stats(self) -> Dict:
        """Export graph statistics for monitoring"""
        return {
            "node_count": self.graph.number_of_nodes(),
            "edge_count": self.graph.number_of_edges(),
            "connected_components": self.get_connected_components(),
            "central_chains": self.get_central_chains(3),
            "last_updated": self.last_updated.isoformat(),
        }

    def update_timestamp(self):
        """Update the last updated timestamp"""
        self.last_updated = datetime.utcnow()


# Singleton instance
_fundamentals_graph_instance: Optional[FundamentalsGraph] = None


def get_fundamentals_graph() -> FundamentalsGraph:
    """Get the singleton instance of FundamentalsGraph"""
    global _fundamentals_graph_instance
    if _fundamentals_graph_instance is None:
        _fundamentals_graph_instance = FundamentalsGraph()
    return _fundamentals_graph_instance
