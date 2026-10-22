// Рекомендации, пока можно получать пустой массив
class Recommendation {
  final List<int> daysToReduce; // Дни, с которых надо убрать работу
  final List<int> daysToMoveTo; // Дни, на которые можно перенести

  Recommendation({required this.daysToReduce, required this.daysToMoveTo});

  factory Recommendation.fromJson(Map<String, dynamic> json) {
    return Recommendation(daysToReduce: List<int>.from(json['daysToReduce'] ?? []), daysToMoveTo: List<int>.from(json['daysToMoveTo'] ?? []));
  }
}
