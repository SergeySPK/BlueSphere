import 'dart:convert';
import 'package:http/http.dart' as http;
import '../core/logger.dart';
import '../domain/school_class.dart';
import '../domain/load_day.dart';
import '../domain/class_status.dart';
import '../domain/recommendation.dart';

// Сервис для взаимодействия с REST API бэкенда
class ApiService {
  static const String baseUrl = 'https://blue-sphere-bot.bothost.tech';

  static String? _token;
  static int? _schoolId;

  // Авторизация пользователя через MAX
  static Future<Map<String, dynamic>?> auth(String initData) async {
    try {
      final response = await http.post(Uri.parse('$baseUrl/api/auth'), headers: {'Content-Type': 'application/json'}, body: jsonEncode({'init_data': initData}));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        _token = data['access_token'];

        final schools = data['schools'] as List?;
        if (schools != null && schools.isNotEmpty) {
          _schoolId = schools[0]['id'];
        }
        return data;
      } else {
        throw Exception(response.statusCode);
      }
    } catch (e, stack) {
      AppLogger.error('Сбой авторизации', error: e, stackTrace: stack, tag: '[API] auth');
      rethrow;
    }
  }

  // Получение списка классов школы (для учителей и админов)
  static Future<Map<String, List<SchoolClass>>> getClasses() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/schools/$_schoolId/classes'), headers: {'Content-Type': 'application/json', if (_token != null) 'Authorization': 'Bearer $_token'});

      if (response.statusCode == 200) {
        final Map<String, dynamic> data = jsonDecode(response.body);
        final Map<String, List<SchoolClass>> result = {};
        data.forEach((parallelName, classesJson) {
          final List<dynamic> list = classesJson;
          result[parallelName] = list.map((json) => SchoolClass.fromJson(json)).toList();
        });
        return result;
      } else {
        throw Exception(response.statusCode);
      }
    } catch (e, stack) {
      AppLogger.error('Сбой загрузки классов', error: e, stackTrace: stack, tag: '[API] getClasses');
      rethrow;
    }
  }

  // Получение тепловой карты нагрузки на месяц
  static Future<List<LoadDay>> getHeatmap(String classId, String month) async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/schools/$_schoolId/classes/$classId/heatmap?month=$month'), headers: {'Content-Type': 'application/json', if (_token != null) 'Authorization': 'Bearer $_token'});

      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);
        return data.map((json) => LoadDay.fromJson(json)).toList();
      } else {
        throw Exception(response.statusCode);
      }
    } catch (e, stack) {
      AppLogger.error('Сбой загрузки тепловой арты', error: e, stackTrace: stack, tag: '[API] getHeatmap');
      rethrow;
    }
  }

  // Получение статуса нагрузки для баннера (на конкретную дату)
  static Future<ClassStatus> getSummary(String classId, String date) async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/schools/$_schoolId/classes/$classId/summary?date=$date'), headers: {'Content-Type': 'application/json', if (_token != null) 'Authorization': 'Bearer $_token'});

      if (response.statusCode == 200) {
        return ClassStatus.fromJson(jsonDecode(response.body));
      } else {
        throw Exception(response.statusCode);
      }
    } catch (e, stack) {
      AppLogger.error('Сбой загрузки статуса', error: e, stackTrace: stack, tag: '[API] getSummary');
      rethrow;
    }
  }

  // Получение рекомендаций от ИИ (доступно только учителям/админам)
  static Future<Recommendation> getRecommendations(String classId) async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/schools/$_schoolId/classes/$classId/recommendations'), headers: {'Content-Type': 'application/json', if (_token != null) 'Authorization': 'Bearer $_token'});

      if (response.statusCode == 200) {
        AppLogger.info('Рекомендации успешно загружены', tag: '[API] getRecommendations');
        return Recommendation.fromJson(jsonDecode(response.body));
      } else {
        throw Exception(response.statusCode);
      }
    } catch (e, stack) {
      AppLogger.error('Сбой загрузки рекомендаций', error: e, stackTrace: stack, tag: '[API] getRecommendations');
      rethrow;
    }
  }

  // Получение расписания на конкретный день
  static Future<List<dynamic>> getSchedule(String classId, String date) async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/schools/$_schoolId/classes/$classId/schedule?date=$date'), headers: {'Content-Type': 'application/json', if (_token != null) 'Authorization': 'Bearer $_token'});

      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      } else {
        throw Exception(response.statusCode);
      }
    } catch (e, stack) {
      AppLogger.error('Сбой загрузки расписания', error: e, stackTrace: stack, tag: '[API] getSchedule');
      rethrow;
    }
  }

  // Обновление типа урока
  static Future<bool> updateLesson(String classId, String lessonId, String newType) async {
    try {
      final response = await http.put(
        Uri.parse('$baseUrl/api/schools/$_schoolId/classes/$classId/schedule/$lessonId'),
        headers: {'Content-Type': 'application/json', if (_token != null) 'Authorization': 'Bearer $_token'},
        body: jsonEncode({'lesson_type': newType}),
      );

      if (response.statusCode == 200) {
        AppLogger.info('Тип урока обновлен (ID: $lessonId)', tag: '[API] updateLesson');
        return true;
      } else {
        throw Exception(response.statusCode);
      }
    } catch (e, stack) {
      AppLogger.error('Сбой обновления урока', error: e, stackTrace: stack, tag: '[API] updateLesson');
      rethrow;
    }
  }

  // Начало сессии редактирования урока
  static Future<void> startEditing(String classId, String lessonId) async {
    try {
      final response = await http.post(Uri.parse('$baseUrl/api/schools/$_schoolId/classes/$classId/schedule/$lessonId/editing'), headers: {if (_token != null) 'Authorization': 'Bearer $_token'});
      if (response.statusCode != 200) throw Exception(response.statusCode);
    } catch (e, stack) {
      AppLogger.error('Сбой старта редактирования', error: e, stackTrace: stack, tag: '[API] startEditing');
      rethrow;
    }
  }

  // Продление активной сессии редактирования
  static Future<void> renewEditing(String classId, String lessonId) async {
    try {
      final response = await http.put(Uri.parse('$baseUrl/api/schools/$_schoolId/classes/$classId/schedule/$lessonId/editing'), headers: {if (_token != null) 'Authorization': 'Bearer $_token'});
      if (response.statusCode != 200) throw Exception(response.statusCode);
    } catch (e, stack) {
      AppLogger.error('Сбой продления редактирования', error: e, stackTrace: stack, tag: '[API] renewEditing');
      rethrow;
    }
  }

  // Завершение сессии редактирования урока
  static Future<void> stopEditing(String classId, String lessonId) async {
    try {
      final response = await http.delete(Uri.parse('$baseUrl/api/schools/$_schoolId/classes/$classId/schedule/$lessonId/editing'), headers: {if (_token != null) 'Authorization': 'Bearer $_token'});
      if (response.statusCode != 200) throw Exception(response.statusCode);
    } catch (e, stack) {
      AppLogger.error('Сбой завершения редактирования', error: e, stackTrace: stack, tag: '[API] stopEditing');
      rethrow;
    }
  }

  // Получение списка опросов для класса
  static Future<List<dynamic>> getClassSurveys(String classId) async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/schools/$_schoolId/classes/$classId/surveys'), headers: {'Content-Type': 'application/json', if (_token != null) 'Authorization': 'Bearer $_token'});
      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      } else {
        throw Exception(response.statusCode);
      }
    } catch (e, stack) {
      AppLogger.error('Сбой загрузки опросов', error: e, stackTrace: stack, tag: '[API] getClassSurveys');
      rethrow;
    }
  }

  // Получение статистики по конкретному опросу
  static Future<Map<String, dynamic>> getSurveyStatistics(String classId, String surveyDate) async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/schools/$_schoolId/classes/$classId/surveys/$surveyDate'), headers: {'Content-Type': 'application/json', if (_token != null) 'Authorization': 'Bearer $_token'});
      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      } else {
        throw Exception(response.statusCode);
      }
    } catch (e, stack) {
      AppLogger.error('Сбой загрузки статистики', error: e, stackTrace: stack, tag: '[API] getSurveyStatistics');
      rethrow;
    }
  }
}
