// для блока с плашками дней на экране "Нагрузка"
class Recommendation {
  final List<int> daysToReduce;
  final List<int> daysToMoveTo;

  Recommendation({required this.daysToReduce, required this.daysToMoveTo});

  factory Recommendation.fromJson(Map<String, dynamic> json) {
    return Recommendation(daysToReduce: List<int>.from(json['daysToReduce'] ?? []), daysToMoveTo: List<int>.from(json['daysToMoveTo'] ?? []));
  }
}

// для текстовых советов ИИ на экране деталей дня
class AiTextRecommendation {
  final String title;
  final String description;

  AiTextRecommendation({required this.title, required this.description});

  factory AiTextRecommendation.fromJson(Map<String, dynamic> json) {
    return AiTextRecommendation(title: json['title'] as String, description: json['description'] as String);
  }
}
