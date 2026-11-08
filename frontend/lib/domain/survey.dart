// Модель одного варианта ответа в опросе
class SurveyResultItem {
  final String label;
  final int percentage;
  final bool isHighlighted;

  SurveyResultItem({required this.label, required this.percentage, this.isHighlighted = false});
}

// Модель одного вопроса с вариантами ответов
class SurveyQuestionResult {
  final String title;
  final List<SurveyResultItem> options;

  SurveyQuestionResult({required this.title, required this.options});
}

// Краткая сводка по вопросу
class SurveyQuestionSummary {
  final String title;
  final String topAnswer;

  const SurveyQuestionSummary({required this.title, required this.topAnswer});
}
