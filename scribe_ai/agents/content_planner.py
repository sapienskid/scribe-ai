class ContentPlanner:
    """Handles content planning and structure"""
    def __init__(self, api):
        self.api = api
        self._setup_system_instructions()

    def _setup_system_instructions(self):
        """Initializes system instructions for content planning"""
        self.system_instructions = {
            "content_planning": """You are an expert content strategist..."""
        }

    async def create_content_plan(self, topic: str, agents: List[Agent]) -> ContentPlan:
        """Creates a detailed content plan"""
        self.api.set_system_instruction(self.system_instructions["content_planning"])
        # Implementation details...