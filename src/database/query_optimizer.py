"""
Database query optimization and batching system.
"""

import asyncio
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
import time

from pymongo import IndexModel, ASCENDING, DESCENDING, TEXT
from pymongo.errors import OperationFailure

from utils.logging_config import get_logger, LoggerMixin


class QueryType(Enum):
    """Types of database queries."""
    
    FIND = "find"
    FIND_ONE = "find_one"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    AGGREGATE = "aggregate"
    COUNT = "count"


@dataclass
class QueryPlan:
    """Execution plan for a database query."""
    
    query_type: QueryType
    collection: str
    filter_dict: Dict[str, Any] = field(default_factory=dict)
    projection: Optional[Dict[str, Any]] = None
    sort: Optional[List[Tuple[str, int]]] = None
    limit: Optional[int] = None
    skip: Optional[int] = None
    update_doc: Optional[Dict[str, Any]] = None
    pipeline: Optional[List[Dict[str, Any]]] = None
    
    def get_cache_key(self) -> str:
        """Generate cache key for this query."""
        key_parts = [
            self.query_type.value,
            self.collection,
            str(sorted(self.filter_dict.items())),
            str(self.projection),
            str(self.sort),
            str(self.limit),
            str(self.skip)
        ]
        return "|".join(str(part) for part in key_parts)


@dataclass
class QueryStats:
    """Statistics for query performance."""
    
    query_type: QueryType
    collection: str
    execution_count: int = 0
    total_time: float = 0.0
    avg_time: float = 0.0
    min_time: float = float('inf')
    max_time: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    
    def update(self, execution_time: float, cache_hit: bool = False) -> None:
        """Update statistics with new execution."""
        self.execution_count += 1
        self.total_time += execution_time
        self.avg_time = self.total_time / self.execution_count
        self.min_time = min(self.min_time, execution_time)
        self.max_time = max(self.max_time, execution_time)
        
        if cache_hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1


class QueryOptimizer(LoggerMixin):
    """
    Database query optimizer with caching, batching, and performance monitoring.
    """
    
    def __init__(self, database_manager, cache_manager=None):
        self.database = database_manager
        self.cache = cache_manager
        
        # Query statistics
        self._query_stats: Dict[str, QueryStats] = {}
        
        # Query batching
        self._pending_queries: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._batch_timers: Dict[str, asyncio.Task] = {}
        self._batch_config = {
            'max_batch_size': 50,
            'max_wait_time': 0.1,  # 100ms
            'enabled_operations': {QueryType.FIND, QueryType.INSERT, QueryType.UPDATE}
        }
        
        # Index recommendations
        self._slow_queries: deque = deque(maxlen=1000)
        self._index_recommendations: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        # Performance thresholds
        self._slow_query_threshold = 1.0  # 1 second
        self._cache_ttl = 300  # 5 minutes
    
    async def execute_query(self, query_plan: QueryPlan) -> Any:
        """
        Execute a database query with optimization.
        
        Args:
            query_plan: Query execution plan
            
        Returns:
            Query result
        """
        start_time = time.time()
        cache_hit = False
        result = None
        
        try:
            # Check cache for read operations
            if query_plan.query_type in {QueryType.FIND, QueryType.FIND_ONE, QueryType.COUNT}:
                result = await self._try_cache_lookup(query_plan)
                if result is not None:
                    cache_hit = True
            
            # Execute query if not cached
            if result is None:
                if self._should_batch_query(query_plan):
                    result = await self._batch_query(query_plan)
                else:
                    result = await self._execute_direct_query(query_plan)
                
                # Cache result for read operations
                if (query_plan.query_type in {QueryType.FIND, QueryType.FIND_ONE, QueryType.COUNT} 
                    and self.cache):
                    await self._cache_result(query_plan, result)
            
            execution_time = time.time() - start_time
            
            # Update statistics
            await self._update_query_stats(query_plan, execution_time, cache_hit)
            
            # Check for slow queries
            if execution_time > self._slow_query_threshold:
                await self._record_slow_query(query_plan, execution_time)
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            await self._update_query_stats(query_plan, execution_time, cache_hit)
            
            self.logger.error(
                f"Query execution failed: {e}",
                extra={
                    'query_type': query_plan.query_type.value,
                    'collection': query_plan.collection,
                    'execution_time': execution_time
                }
            )
            raise
    
    async def _try_cache_lookup(self, query_plan: QueryPlan) -> Optional[Any]:
        """Try to get result from cache."""
        if not self.cache:
            return None
        
        cache_key = f"query:{query_plan.get_cache_key()}"
        return await self.cache.get(cache_key)
    
    async def _cache_result(self, query_plan: QueryPlan, result: Any) -> None:
        """Cache query result."""
        if not self.cache:
            return
        
        cache_key = f"query:{query_plan.get_cache_key()}"
        await self.cache.set(cache_key, result, ttl=self._cache_ttl)
    
    def _should_batch_query(self, query_plan: QueryPlan) -> bool:
        """Check if query should be batched."""
        return (
            query_plan.query_type in self._batch_config['enabled_operations'] and
            query_plan.query_type != QueryType.FIND_ONE  # Single results can't be batched effectively
        )
    
    async def _batch_query(self, query_plan: QueryPlan) -> Any:
        """Add query to batch or execute if batch is ready."""
        batch_key = f"{query_plan.query_type.value}:{query_plan.collection}"
        
        # Create query item
        query_item = {
            'plan': query_plan,
            'future': asyncio.Future(),
            'added_at': time.time()
        }
        
        self._pending_queries[batch_key].append(query_item)
        
        # Check if batch is ready
        if len(self._pending_queries[batch_key]) >= self._batch_config['max_batch_size']:
            await self._execute_batch(batch_key)
        else:
            # Set timer for batch execution
            if batch_key not in self._batch_timers:
                self._batch_timers[batch_key] = asyncio.create_task(
                    self._batch_timer(batch_key)
                )
        
        # Wait for result
        return await query_item['future']
    
    async def _batch_timer(self, batch_key: str) -> None:
        """Timer for batch execution."""
        try:
            await asyncio.sleep(self._batch_config['max_wait_time'])
            if batch_key in self._pending_queries and self._pending_queries[batch_key]:
                await self._execute_batch(batch_key)
        except asyncio.CancelledError:
            pass
        finally:
            self._batch_timers.pop(batch_key, None)
    
    async def _execute_batch(self, batch_key: str) -> None:
        """Execute a batch of queries."""
        if batch_key not in self._pending_queries:
            return
        
        queries = self._pending_queries.pop(batch_key, [])
        if not queries:
            return
        
        # Cancel timer
        if batch_key in self._batch_timers:
            self._batch_timers[batch_key].cancel()
            del self._batch_timers[batch_key]
        
        query_type_str, collection = batch_key.split(':', 1)
        query_type = QueryType(query_type_str)
        
        try:
            if query_type == QueryType.FIND:
                await self._execute_find_batch(collection, queries)
            elif query_type == QueryType.INSERT:
                await self._execute_insert_batch(collection, queries)
            elif query_type == QueryType.UPDATE:
                await self._execute_update_batch(collection, queries)
            else:
                # Fallback to individual execution
                for query_item in queries:
                    try:
                        result = await self._execute_direct_query(query_item['plan'])
                        query_item['future'].set_result(result)
                    except Exception as e:
                        query_item['future'].set_exception(e)
        
        except Exception as e:
            # Set exception for all queries in batch
            for query_item in queries:
                if not query_item['future'].done():
                    query_item['future'].set_exception(e)
    
    async def _execute_find_batch(self, collection: str, queries: List[Dict[str, Any]]) -> None:
        """Execute a batch of find queries using aggregation."""
        try:
            # Group similar queries
            query_groups = defaultdict(list)
            
            for query_item in queries:
                plan = query_item['plan']
                group_key = (
                    str(plan.projection),
                    str(plan.sort),
                    plan.limit,
                    plan.skip
                )
                query_groups[group_key].append(query_item)
            
            # Execute each group
            for group_queries in query_groups.values():
                if len(group_queries) == 1:
                    # Single query, execute directly
                    query_item = group_queries[0]
                    result = await self._execute_direct_query(query_item['plan'])
                    query_item['future'].set_result(result)
                else:
                    # Multiple queries, use $facet aggregation
                    await self._execute_faceted_find(collection, group_queries)
        
        except Exception as e:
            for query_item in queries:
                if not query_item['future'].done():
                    query_item['future'].set_exception(e)
    
    async def _execute_faceted_find(self, collection: str, queries: List[Dict[str, Any]]) -> None:
        """Execute multiple find queries using $facet aggregation."""
        facets = {}
        query_map = {}
        
        for i, query_item in enumerate(queries):
            plan = query_item['plan']
            facet_name = f"query_{i}"
            
            # Build facet pipeline
            pipeline = []
            
            if plan.filter_dict:
                pipeline.append({"$match": plan.filter_dict})
            
            if plan.sort:
                sort_dict = {field: direction for field, direction in plan.sort}
                pipeline.append({"$sort": sort_dict})
            
            if plan.skip:
                pipeline.append({"$skip": plan.skip})
            
            if plan.limit:
                pipeline.append({"$limit": plan.limit})
            
            if plan.projection:
                pipeline.append({"$project": plan.projection})
            
            facets[facet_name] = pipeline
            query_map[facet_name] = query_item
        
        # Execute faceted aggregation
        pipeline = [{"$facet": facets}]
        
        try:
            cursor = self.database[collection].aggregate(pipeline)
            results = await cursor.to_list(length=1)
            
            if results:
                facet_results = results[0]
                
                # Set results for each query
                for facet_name, result in facet_results.items():
                    query_item = query_map[facet_name]
                    query_item['future'].set_result(result)
            else:
                # No results, set empty lists
                for query_item in queries:
                    query_item['future'].set_result([])
        
        except Exception as e:
            for query_item in queries:
                if not query_item['future'].done():
                    query_item['future'].set_exception(e)
    
    async def _execute_insert_batch(self, collection: str, queries: List[Dict[str, Any]]) -> None:
        """Execute a batch of insert queries."""
        documents = []
        
        for query_item in queries:
            plan = query_item['plan']
            if 'document' in plan.filter_dict:
                documents.append(plan.filter_dict['document'])
        
        if documents:
            try:
                result = await self.database[collection].insert_many(documents)
                
                # Set results for each query
                for i, query_item in enumerate(queries):
                    if i < len(result.inserted_ids):
                        query_item['future'].set_result(str(result.inserted_ids[i]))
                    else:
                        query_item['future'].set_result(None)
            
            except Exception as e:
                for query_item in queries:
                    if not query_item['future'].done():
                        query_item['future'].set_exception(e)
    
    async def _execute_update_batch(self, collection: str, queries: List[Dict[str, Any]]) -> None:
        """Execute a batch of update queries using bulk operations."""
        from pymongo import UpdateOne, UpdateMany
        
        bulk_ops = []
        query_items = []
        
        for query_item in queries:
            plan = query_item['plan']
            
            if plan.update_doc:
                # Determine if it's update_one or update_many based on filter
                if '_id' in plan.filter_dict:
                    bulk_ops.append(UpdateOne(plan.filter_dict, plan.update_doc))
                else:
                    bulk_ops.append(UpdateMany(plan.filter_dict, plan.update_doc))
                
                query_items.append(query_item)
        
        if bulk_ops:
            try:
                result = await self.database[collection].bulk_write(bulk_ops)
                
                # Set results for each query
                for query_item in query_items:
                    query_item['future'].set_result(result.modified_count > 0)
            
            except Exception as e:
                for query_item in query_items:
                    if not query_item['future'].done():
                        query_item['future'].set_exception(e)
    
    async def _execute_direct_query(self, query_plan: QueryPlan) -> Any:
        """Execute query directly without batching."""
        if query_plan.query_type == QueryType.FIND:
            return await self._execute_find(query_plan)
        elif query_plan.query_type == QueryType.FIND_ONE:
            return await self._execute_find_one(query_plan)
        elif query_plan.query_type == QueryType.INSERT:
            return await self._execute_insert(query_plan)
        elif query_plan.query_type == QueryType.UPDATE:
            return await self._execute_update(query_plan)
        elif query_plan.query_type == QueryType.DELETE:
            return await self._execute_delete(query_plan)
        elif query_plan.query_type == QueryType.AGGREGATE:
            return await self._execute_aggregate(query_plan)
        elif query_plan.query_type == QueryType.COUNT:
            return await self._execute_count(query_plan)
        else:
            raise ValueError(f"Unsupported query type: {query_plan.query_type}")
    
    async def _execute_find(self, query_plan: QueryPlan) -> List[Dict[str, Any]]:
        """Execute find query."""
        cursor = self.database[query_plan.collection].find(
            query_plan.filter_dict,
            query_plan.projection
        )
        
        if query_plan.sort:
            cursor = cursor.sort(query_plan.sort)
        if query_plan.skip:
            cursor = cursor.skip(query_plan.skip)
        if query_plan.limit:
            cursor = cursor.limit(query_plan.limit)
        
        return await cursor.to_list(length=query_plan.limit)
    
    async def _execute_find_one(self, query_plan: QueryPlan) -> Optional[Dict[str, Any]]:
        """Execute find_one query."""
        return await self.database[query_plan.collection].find_one(
            query_plan.filter_dict,
            query_plan.projection
        )
    
    async def _execute_insert(self, query_plan: QueryPlan) -> str:
        """Execute insert query."""
        document = query_plan.filter_dict.get('document')
        if not document:
            raise ValueError("Insert query requires 'document' in filter_dict")
        
        result = await self.database[query_plan.collection].insert_one(document)
        return str(result.inserted_id)
    
    async def _execute_update(self, query_plan: QueryPlan) -> bool:
        """Execute update query."""
        if not query_plan.update_doc:
            raise ValueError("Update query requires update_doc")
        
        result = await self.database[query_plan.collection].update_one(
            query_plan.filter_dict,
            query_plan.update_doc
        )
        return result.modified_count > 0
    
    async def _execute_delete(self, query_plan: QueryPlan) -> bool:
        """Execute delete query."""
        result = await self.database[query_plan.collection].delete_one(
            query_plan.filter_dict
        )
        return result.deleted_count > 0
    
    async def _execute_aggregate(self, query_plan: QueryPlan) -> List[Dict[str, Any]]:
        """Execute aggregation query."""
        if not query_plan.pipeline:
            raise ValueError("Aggregate query requires pipeline")
        
        cursor = self.database[query_plan.collection].aggregate(query_plan.pipeline)
        return await cursor.to_list(length=None)
    
    async def _execute_count(self, query_plan: QueryPlan) -> int:
        """Execute count query."""
        return await self.database[query_plan.collection].count_documents(
            query_plan.filter_dict
        )
    
    async def _update_query_stats(
        self,
        query_plan: QueryPlan,
        execution_time: float,
        cache_hit: bool
    ) -> None:
        """Update query statistics."""
        stats_key = f"{query_plan.query_type.value}:{query_plan.collection}"
        
        if stats_key not in self._query_stats:
            self._query_stats[stats_key] = QueryStats(
                query_type=query_plan.query_type,
                collection=query_plan.collection
            )
        
        self._query_stats[stats_key].update(execution_time, cache_hit)
    
    async def _record_slow_query(self, query_plan: QueryPlan, execution_time: float) -> None:
        """Record slow query for analysis."""
        slow_query = {
            'timestamp': time.time(),
            'execution_time': execution_time,
            'query_type': query_plan.query_type.value,
            'collection': query_plan.collection,
            'filter': query_plan.filter_dict,
            'projection': query_plan.projection,
            'sort': query_plan.sort,
            'limit': query_plan.limit,
            'skip': query_plan.skip
        }
        
        self._slow_queries.append(slow_query)
        
        # Generate index recommendations
        await self._analyze_slow_query(slow_query)
        
        self.logger.warning(
            f"Slow query detected: {execution_time:.2f}s",
            extra=slow_query
        )
    
    async def _analyze_slow_query(self, slow_query: Dict[str, Any]) -> None:
        """Analyze slow query and generate index recommendations."""
        collection = slow_query['collection']
        filter_dict = slow_query.get('filter', {})
        sort_fields = slow_query.get('sort', [])
        
        recommendations = []
        
        # Recommend indexes for filter fields
        for field in filter_dict.keys():
            if field not in ['$and', '$or', '$nor']:  # Skip logical operators
                recommendations.append({
                    'type': 'filter_index',
                    'fields': [(field, ASCENDING)],
                    'reason': f'Filtering on {field}'
                })
        
        # Recommend indexes for sort fields
        if sort_fields:
            recommendations.append({
                'type': 'sort_index',
                'fields': sort_fields,
                'reason': 'Sorting optimization'
            })
        
        # Recommend compound indexes for filter + sort
        if filter_dict and sort_fields:
            filter_fields = [(field, ASCENDING) for field in filter_dict.keys() 
                           if field not in ['$and', '$or', '$nor']]
            compound_fields = filter_fields + sort_fields
            
            recommendations.append({
                'type': 'compound_index',
                'fields': compound_fields,
                'reason': 'Filter and sort optimization'
            })
        
        # Store recommendations
        for rec in recommendations:
            if rec not in self._index_recommendations[collection]:
                self._index_recommendations[collection].append(rec)
    
    async def create_recommended_indexes(self, collection: str = None) -> Dict[str, List[str]]:
        """Create recommended indexes."""
        results = {}
        
        collections = [collection] if collection else self._index_recommendations.keys()
        
        for coll in collections:
            if coll not in self._index_recommendations:
                continue
            
            created_indexes = []
            
            for recommendation in self._index_recommendations[coll]:
                try:
                    index_model = IndexModel(recommendation['fields'])
                    index_name = await self.database[coll].create_indexes([index_model])
                    
                    created_indexes.append(f"{index_name[0]} - {recommendation['reason']}")
                    
                    self.logger.info(
                        f"Created index on {coll}: {recommendation['fields']} - {recommendation['reason']}"
                    )
                
                except OperationFailure as e:
                    self.logger.warning(f"Failed to create index on {coll}: {e}")
            
            results[coll] = created_indexes
            
            # Clear recommendations after creating indexes
            self._index_recommendations[coll] = []
        
        return results
    
    def get_query_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get query performance statistics."""
        stats = {}
        
        for key, query_stats in self._query_stats.items():
            stats[key] = {
                'query_type': query_stats.query_type.value,
                'collection': query_stats.collection,
                'execution_count': query_stats.execution_count,
                'avg_time': query_stats.avg_time,
                'min_time': query_stats.min_time,
                'max_time': query_stats.max_time,
                'total_time': query_stats.total_time,
                'cache_hits': query_stats.cache_hits,
                'cache_misses': query_stats.cache_misses,
                'cache_hit_rate': (
                    query_stats.cache_hits / (query_stats.cache_hits + query_stats.cache_misses) * 100
                    if (query_stats.cache_hits + query_stats.cache_misses) > 0 else 0
                )
            }
        
        return stats
    
    def get_slow_queries(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent slow queries."""
        return list(self._slow_queries)[-limit:]
    
    def get_index_recommendations(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get index recommendations."""
        return dict(self._index_recommendations)
    
    def clear_stats(self) -> None:
        """Clear query statistics."""
        self._query_stats.clear()
        self._slow_queries.clear()
        self._index_recommendations.clear()
    
    async def invalidate_cache(self, pattern: str = None) -> int:
        """Invalidate query cache."""
        if not self.cache:
            return 0
        
        if pattern:
            return await self.cache.invalidate_pattern(f"query:{pattern}")
        else:
            return await self.cache.invalidate_pattern("query:*")