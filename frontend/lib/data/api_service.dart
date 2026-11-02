import 'dart:convert';
import 'package:http/http.dart' as http;
import '../domain/school_class.dart';
import '../domain/load_day.dart';
import '../domain/class_status.dart';
import '../domain/recommendation.dart';

class ApiService {
  static const String baseUrl = 'https://blue-sphere-bot.bothost.tech';

  static String? _token;
  static int? _schoolId; // <-- Храним ID школы
  static List<String>? _roles;

  static void setTestToken(String token) {
    _token = token;
  }

  static void setTestSchoolId(int id) {
    _schoolId = id;
  }

  // 1. Авторизация
  static Future<Map<String, dynamic>?> auth(String initData) async {
    try {
      final response = await http.post(Uri.parse('$baseUrl/api/auth'), headers: {'Content-Type': 'application/json'}, body: jsonEncode({'init_data': initData}));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        _token = data['access_token'];
        _roles = List<String>.from(data['roles'] ?? []);

        // --- СОХРАНЯЕМ ID ШКОЛЫ ---
        final schools = data['schools'] as List?;
        if (schools != null && schools.isNotEmpty) {
          _schoolId = schools[0]['id'];
          print('Школа ID: $_schoolId');
        }

        return data;
      } else {
        throw Exception(response.statusCode);
      }
    } catch (e) {
      print('Ошибка auth: $e');
      rethrow;
    }
  }

  // 2. Получение классов (для учителя/админа)
  static Future<Map<String, List<SchoolClass>>> getClasses() async {
    try {
      // Новый путь с ID школы
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
    } catch (e) {
      print('Ошибка getClasses: $e');
      rethrow;
    }
  }

  // 3. Календарь (Тепловая карта)
  static Future<List<LoadDay>> getHeatmap(String classId, String month) async {
    try {
      // Новый путь
      final response = await http.get(Uri.parse('$baseUrl/api/schools/$_schoolId/classes/$classId/heatmap?month=$month'), headers: {'Content-Type': 'application/json', if (_token != null) 'Authorization': 'Bearer $_token'});

      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);
        return data.map((json) => LoadDay.fromJson(json)).toList();
      } else {
        throw Exception(response.statusCode);
      }
    } catch (e) {
      print('Ошибка getHeatmap: $e');
      rethrow;
    }
  }

  // 4. Статус для баннера
  static Future<ClassStatus> getSummary(String classId, String date) async {
    try {
      // Новый путь
      final response = await http.get(Uri.parse('$baseUrl/api/schools/$_schoolId/classes/$classId/summary?date=$date'), headers: {'Content-Type': 'application/json', if (_token != null) 'Authorization': 'Bearer $_token'});

      if (response.statusCode == 200) {
        return ClassStatus.fromJson(jsonDecode(response.body));
      } else {
        throw Exception(response.statusCode);
      }
    } catch (e) {
      print('Ошибка getSummary: $e');
      rethrow;
    }
  }

  // 5. Рекомендации
  static Future<Recommendation> getRecommendations(String classId) async {
    try {
      // Новый путь
      final response = await http.get(Uri.parse('$baseUrl/api/schools/$_schoolId/classes/$classId/recommendations'), headers: {'Content-Type': 'application/json', if (_token != null) 'Authorization': 'Bearer $_token'});

      if (response.statusCode == 200) {
        return Recommendation.fromJson(jsonDecode(response.body));
      } else {
        throw Exception(response.statusCode);
      }
    } catch (e) {
      print('Ошибка getRecommendations: $e');
      rethrow;
    }
  }

  // 6. Расписание на день
  static Future<List<dynamic>> getSchedule(String classId, String date) async {
    try {
      // Новый путь
      final response = await http.get(Uri.parse('$baseUrl/api/schools/$_schoolId/classes/$classId/schedule?date=$date'), headers: {'Content-Type': 'application/json', if (_token != null) 'Authorization': 'Bearer $_token'});

      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      } else {
        throw Exception(response.statusCode);
      }
    } catch (e) {
      print('Ошибка getSchedule: $e');
      rethrow;
    }
  }

  // 7. Обновление типа урока
  static Future<bool> updateLesson(String lessonId, String newType) async {
    try {
      final response = await http.put(Uri.parse('$baseUrl/api/schedule/$lessonId'), headers: {'Content-Type': 'application/json', if (_token != null) 'Authorization': 'Bearer $_token'}, body: jsonEncode({'lesson_type': newType}));

      if (response.statusCode == 200) {
        return true;
      } else {
        throw Exception(response.statusCode);
      }
    } catch (e) {
      print('Ошибка updateLesson: $e');
      rethrow;
    }
  }

  // 8. Начать редактирование
  static Future<void> startEditing(String lessonId) async {
    try {
      final response = await http.post(Uri.parse('$baseUrl/api/schedule/$lessonId/editing'), headers: {if (_token != null) 'Authorization': 'Bearer $_token'});
      if (response.statusCode != 200) throw Exception(response.statusCode);
    } catch (e) {
      print('Ошибка startEditing: $e');
      rethrow;
    }
  }

  // 9. Продлить редактирование
  static Future<void> renewEditing(String lessonId) async {
    try {
      final response = await http.put(Uri.parse('$baseUrl/api/schedule/$lessonId/editing'), headers: {if (_token != null) 'Authorization': 'Bearer $_token'});
      if (response.statusCode != 200) throw Exception(response.statusCode);
    } catch (e) {
      print('Ошибка renewEditing: $e');
      rethrow;
    }
  }

  // 10. Закончить редактирование
  static Future<void> stopEditing(String lessonId) async {
    try {
      final response = await http.delete(Uri.parse('$baseUrl/api/schedule/$lessonId/editing'), headers: {if (_token != null) 'Authorization': 'Bearer $_token'});
      if (response.statusCode != 200) throw Exception(response.statusCode);
    } catch (e) {
      print('Ошибка stopEditing: $e');
      rethrow;
    }
  }
}
