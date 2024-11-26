class ContentFormatter:
    """Handles formatting and citation management"""
    def __init__(self):
        self.citations: List[Citation] = []

    def generate_markdown(
        self,
        content_plan: ContentPlan,
        research_results: Dict[str, Any]
    ) -> str:
        """Generates formatted markdown with citations"""
        # Implementation details...

    def _format_citation(self, citation: Citation) -> str:
        """Formats a single citation"""
        # Implementation details...