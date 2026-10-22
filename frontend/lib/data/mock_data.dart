import '../models/school_class.dart';
import '../models/load_day.dart';
import '../models/recommendation.dart';
import '../models/class_status.dart';
// Фейковые данные

// Моковые данные классов
final Map<String, List<SchoolClass>> mockClasses = {
  for (int i = 1; i <= 11; i++)
    '$i класс': [
      SchoolClass(id: '${i}a', name: 'Класс $iА'),
      SchoolClass(id: '${i}b', name: 'Класс $iБ'),
      SchoolClass(id: '${i}v', name: 'Класс $iВ'),
      SchoolClass(id: '${i}g', name: 'Класс $iГ'),
      SchoolClass(id: '${i}d', name: 'Класс $iД'),
    ],
};

// Моковые данные нагрузки
final List<LoadDay> mockLoadDays = [
  LoadDay(day: 1, level: 1),
  LoadDay(day: 2, level: 1),
  LoadDay(day: 3, level: 0),
  LoadDay(day: 4, level: 0),
  LoadDay(day: 5, level: 2),
  LoadDay(day: 6, level: 3),
  LoadDay(day: 7, level: 2),
  LoadDay(day: 8, level: 1),
  LoadDay(day: 9, level: 0),
  LoadDay(day: 10, level: 0),
  LoadDay(day: 11, level: 1),
  LoadDay(day: 12, level: 2),
  LoadDay(day: 13, level: 1),
  LoadDay(day: 14, level: 2),
  LoadDay(day: 15, level: 3),
  LoadDay(day: 16, level: 2),
  LoadDay(day: 17, level: 0),
  LoadDay(day: 18, level: 1),
  LoadDay(day: 19, level: 1),
  LoadDay(day: 20, level: 0),
  LoadDay(day: 21, level: 3),
  LoadDay(day: 22, level: 4),
  LoadDay(day: 23, level: 3),
  LoadDay(day: 24, level: 0),
  LoadDay(day: 25, level: 2),
  LoadDay(day: 26, level: 1),
  LoadDay(day: 27, level: 0),
  LoadDay(day: 28, level: 2),
  LoadDay(day: 29, level: 3),
  LoadDay(day: 30, level: 0),
  LoadDay(day: 31, level: 0),
];

// Моковые рекомендации от ИИ
final Recommendation mockRecommendation = Recommendation(daysToReduce: [31, 26, 24, 20, 11, 9, 6], daysToMoveTo: [5, 16, 23, 30]);

// Моковый статус класса
final ClassStatus mockClassStatus = ClassStatus(level: 4, date: '09.09');
