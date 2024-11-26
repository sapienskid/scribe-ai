from scribe_ai.agents.imports import *
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ContentPlanner:
    """Handles content planning and structure"""
    def __init__(self, api):
        self.api = api
        self._setup_system_instructions()

    def _setup_system_instructions(self):
        """Initializes system instructions for content planning"""
        self.system_instructions = {
            "content_planning": """You are an expert content strategist and outline architect.
            Your role is to:
            - Create comprehensive content plans
            - Structure logical section flow
            - Define clear research requirements
            - Align content with audience needs
            - Establish measurable content goals
            
            Deliver structured content plans in JSON format with clear section progression and research needs.""",
                               
        }

    async def create_content_plan(self, topic: str, agents: List[Agent]) -> ContentPlan:
        """Creates a detailed content plan"""
        self.api.set_system_instruction(self.system_instructions["content_planning"])
        try:
            if not self.agents:
                await self.create_agents(topic)

            plan_prompt = {
                "role": "user",
                "content": f"""Create a detailed content plan for '{topic}'.
                Return JSON with:
                - target_audience: intended readers
                - content_type: type of content
                - sections: array of sections with title and description
                - research_requirements: needed research by area
                - required_expertise: needed knowledge areas
                - content_goals: what the content should achieve"""
            }

            response = await self.api.generate_content(json.dumps(plan_prompt))
            if not response:
                logger.warning("No API response for content plan, using default")
                return ContentPlan._create_default(topic)

            return ContentPlan.from_api_response(response, topic)

        except Exception as e:
            logger.error(f"Error creating content plan: {str(e)}")
            return ContentPlan._create_default(topic)