class ContentCreationOrchestrator:
    """Main orchestrator class that coordinates all components"""
    def __init__(self, api, research_orchestrator):
        self.research_manager = ResearchManager(research_orchestrator)
        self.agent_manager = AgentManager(api)
        self.content_planner = ContentPlanner(api)
        self.content_generator = ContentGenerator(api)
        self.content_formatter = ContentFormatter()

    async def create_content(self, topic: str) -> str:
        """Main method to orchestrate content creation process"""
        try:
            # Create agents
            agents = await self.agent_manager.create_agents(topic)

            # Create content plan
            content_plan = await self.content_planner.create_content_plan(topic, agents)

            # Conduct research
            research_results = await self.research_manager.conduct_research(topic, content_plan)

            # Generate content for each section
            completed_sections = []
            all_sections_content = []

            for section in content_plan.sections:
                content = await self.content_generator.create_section_content(
                    section,
                    content_plan,
                    research_results,
                    completed_sections
                )
                section.content = content
                completed_sections.append(section)
                all_sections_content.append({
                    "title": section.title,
                    "content": content
                })

            # Create introduction and conclusion
            introduction, conclusion = await self.content_generator.create_introduction_conclusion(
                content_plan,
                research_results,
                all_sections_content
            )
            content_plan.introduction = introduction
            content_plan.conclusion = conclusion

            # Format final content
            return self.content_formatter.generate_markdown(content_plan, research_results)

        except Exception as e:
            logging.error(f"Error in content creation: {str(e)}")
            raise