// Модель данных для рекомендаций и прогнозов нагрузки от ИИ
class Recommendation {
  final List<int> daysToReduce; // Дни, где нужно снизить нагрузку
  final List<int> daysToMoveTo; // Дни, куда можно перенести задания
  final String analysisStatus; // Статус ИИ
  final bool isStale; // Флаг: данные устарели
  final Period? period; // Период, за который сделан прогноз
  final List<DailyLoad> dailyLoads; // Детальные прогнозы по дням
  final List<AiRecommendationItem> recommendations; // Текстовые советы от ИИ
  final String dataSource; // Источник данных

  Recommendation({required this.daysToReduce, required this.daysToMoveTo, required this.analysisStatus, required this.isStale, this.period, required this.dailyLoads, required this.recommendations, required this.dataSource});

  // Парсинг JSON-ответа от сервера
  factory Recommendation.fromJson(Map<String, dynamic> json) {
    return Recommendation(
      daysToReduce: List<int>.from(json['daysToReduce'] ?? []),
      daysToMoveTo: List<int>.from(json['daysToMoveTo'] ?? []),
      analysisStatus: json['analysisStatus'] as String? ?? 'not_started',
      isStale: json['isStale'] as bool? ?? false,
      period: json['period'] != null ? Period.fromJson(json['period']) : null,
      dailyLoads: (json['dailyLoads'] as List? ?? []).map((e) => DailyLoad.fromJson(e)).toList(),
      recommendations: (json['recommendations'] as List? ?? []).map((e) => AiRecommendationItem.fromJson(e)).toList(),
      dataSource: json['dataSource'] as String? ?? 'schedule',
    );
  }
}

// Модель временного периода, за который сделан прогноз
class Period {
  final String start; // Дата начала
  final String end; // Дата окончания

  Period({required this.start, required this.end});

  factory Period.fromJson(Map<String, dynamic> json) {
    return Period(start: json['start'] as String, end: json['end'] as String);
  }
}

// Модель дневного прогноза нагрузки
class DailyLoad {
  final String date; // Дата
  final int day; // Номер дня месяца
  final int level; // Уровень нагрузки
  final String source; // Источник

  DailyLoad({required this.date, required this.day, required this.level, required this.source});

  factory DailyLoad.fromJson(Map<String, dynamic> json) {
    return DailyLoad(date: json['date'] as String, day: json['day'] as int, level: json['level'] as int, source: json['source'] as String);
  }
}

// Модель для конкретного текстового совета от ИИ
class AiRecommendationItem {
  final String date; // Дата, к которой относится совет
  final String kind; // Тип: class, teacher, lesson
  final String priority; // Приоритет: low, normal, high, critical
  final String title; // Заголовок совета
  final String recommendationText; // Основной текст рекомендации
  final String? rationale; // Обоснование
  final int? teacherId; // ID учителя
  final int? scheduleId; // ID урока

  AiRecommendationItem({required this.date, required this.kind, required this.priority, required this.title, required this.recommendationText, this.rationale, this.teacherId, this.scheduleId});

  factory AiRecommendationItem.fromJson(Map<String, dynamic> json) {
    return AiRecommendationItem(
      date: json['date'] as String,
      kind: json['kind'] as String,
      priority: json['priority'] as String,
      title: json['title'] as String,
      recommendationText: json['recommendationText'] as String,
      rationale: json['rationale'] as String?,
      teacherId: json['teacherId'] as int?,
      scheduleId: json['scheduleId'] as int?,
    );
  }
}
