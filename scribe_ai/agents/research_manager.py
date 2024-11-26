from scribe_ai.agents.imports import *
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
class ResearchManager:
    """Handles all research-related operations and caching"""
    def __init__(self, research_orchestrator, cache_dir: Path = Path("research_cache")):
        self.research_orchestrator = research_orchestrator
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(exist_ok=True)

    async def conduct_research(self, topic: str, content_plan: ContentPlan) -> Dict[str, Any]:
        """Main research method that checks cache and conducts new research if needed"""
        cached_results = await self._get_cached_research(topic)
        if cached_results:
            return cached_results

        research_results = await self._perform_research(topic, content_plan)
        await self._cache_research_results(topic, research_results)
        return research_results

    async def _perform_research(self, topic: str, content_plan: ContentPlan) -> Dict[str, Any]:
        """Conducts actual research using the research orchestrator"""
        research_prompt = {
            "topic": topic,
            "content_type": content_plan.content_type,
            "audience": content_plan.target_audience,
            "research_requirements": content_plan.research_requirements,
            "sections": [{"title": s.title, "description": s.description} for s in content_plan.sections]
        }
        return await self.research_orchestrator.conduct_research(json.dumps(research_prompt))

    async def _get_cached_research(self, topic: str) -> Optional[Dict[str, Any]]:
        """Retrieves cached research results"""
        cache_file = self._get_cache_filename(topic)
        if cache_file.exists():
            try:
                with cache_file.open('r') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Error reading cache file: {str(e)}")
        return None

    async def _cache_research_results(self, topic: str, results: Dict[str, Any]):
        """Saves research results to cache"""
        cache_file = self._get_cache_filename(topic)
        try:
            with cache_file.open('w') as f:
                json.dump(results, f)
        except Exception as e:
            logging.error(f"Error writing to cache file: {str(e)}")

    def _get_cache_filename(self, topic: str) -> Path:
        """Generates unique filename for caching"""
        topic_hash = hashlib.md5(topic.encode()).hexdigest()
        return self.cache_dir / f"research_{topic_hash}.json"