// Модель рекомендаций для экрана Нагрузка
class Recommendation {
  final List<int> daysToReduce; // Дни перегрузки
  final List<int> daysToMoveTo; // Дни разгрузки

  Recommendation({required this.daysToReduce, required this.daysToMoveTo});

  factory Recommendation.fromJson(Map<String, dynamic> json) {
    return Recommendation(daysToReduce: List<int>.from(json['daysToReduce'] ?? []), daysToMoveTo: List<int>.from(json['daysToMoveTo'] ?? []));
  }
}

// Модель текстовых рекомендаций от ИИ
class AiTextRecommendation {
  final String title; // Заголовок совета
  final String description; // Текст совета

  AiTextRecommendation({required this.title, required this.description});

  factory AiTextRecommendation.fromJson(Map<String, dynamic> json) {
    return AiTextRecommendation(title: json['title'] as String, description: json['description'] as String);
  }
}
