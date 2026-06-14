from project_analyzer.core import ProjectAnalyzer
from project_analyzer.models import ProjectType

def test_analyze_real_project_full():
    analyzer = ProjectAnalyzer()
    path = "/home/usr/react-e-commerce-project"
    result = analyzer.analyze(path)
    print("\n")
    print(result.summary())
