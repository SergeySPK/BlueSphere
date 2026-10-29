import 'dart:convert';
import 'package:flutter_max_miniapp/flutter_max_miniapp.dart';
import 'package:http/http.dart' as http;
import '../domain/school_class.dart';
import '../domain/load_day.dart';
import '../domain/class_status.dart';
import '../domain/recommendation.dart';

class ApiService {
  static const String baseUrl = 'https://blue-sphere-bot.bothost.tech';

  // получение роли
  static Future<Map<String, dynamic>?> auth() async {
    try {
      // Получаем строку initData прямо из библиотеки MAX
      final initData = MaxWebApp().initData;
      if (initData == null || initData.isEmpty) {
        print('initData пустой (мы не в MAX)');
        return null;
      }
      final response = await http.post(
        Uri.parse('$baseUrl/api/auth'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'init_data': initData}), // Отправляем её
      );
      if (response.statusCode == 200) {
        return jsonDecode(response.body); // Тут вернется JWT токен и роль
      }
      return null;
    } catch (e) {
      print('Ошибка auth: $e');
      return null;
    }
  }

  // получение списка классов
  static Future<Map<String, List<SchoolClass>>?> getClasses() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/classes'));
      if (response.statusCode == 200) {
        final Map<String, dynamic> data = jsonDecode(response.body);
        final Map<String, List<SchoolClass>> result = {};

        data.forEach((parallelName, classesJson) {
          final List<dynamic> list = classesJson;
          result[parallelName] = list.map((json) => SchoolClass.fromJson(json)).toList();
        });
        return result;
      }
      return null;
    } catch (e) {
      print('Ошибка getClasses: $e');
      return null;
    }
  }

  // календарь
  static Future<List<LoadDay>?> getHeatmap(String classId, String month) async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/classes/$classId/heatmap?month=$month'));
      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);
        return data.map((json) => LoadDay.fromJson(json)).toList();
      }
      return null;
    } catch (e) {
      print('Ошибка getHeatmap: $e');
      return null;
    }
  }

  // статус для баннера
  static Future<ClassStatus?> getSummary(String classId, String date) async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/classes/$classId/summary?date=$date'));
      if (response.statusCode == 200) {
        // если в JSON нет поля level, fromJson вернет null, и это нормально
        return ClassStatus.fromJson(jsonDecode(response.body));
      }
      return null;
    } catch (e) {
      print('Ошибка getSummary: $e');
      return null;
    }
  }

  // получение расписания на день
  static Future<List<dynamic>?> getSchedule(String classId, String date) async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/classes/$classId/schedule?date=$date'));
      if (response.statusCode == 200) {
        return jsonDecode(response.body); // возвращает массив
      }
      return null;
    } catch (e) {
      print('Ошибка getSchedule: $e');
      return null;
    }
  }

  // рекомендации
  static Future<Recommendation?> getRecommendations(String classId) async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/classes/$classId/recommendations'));
      if (response.statusCode == 200) {
        return Recommendation.fromJson(jsonDecode(response.body));
      }
      return null;
    } catch (e) {
      print('Ошибка getRecommendations: $e');
      return null;
    }
  }

  // обновление типа урока
  static Future<bool> updateLesson(String lessonId, String newType, String teacherSferumId) async {
    try {
      final response = await http.put(
        Uri.parse('$baseUrl/api/schedule/$lessonId'),
        headers: {
          'Content-Type': 'application/json',
          // 'Authorization': 'Bearer $token', // раскомментим, когда будет токен
        },
        body: jsonEncode({'lesson_type': newType, 'updated_by_sferum_id': teacherSferumId}),
      );

      if (response.statusCode == 200) {
        return true;
      } else {
        print('Сервер вернул ошибку: ${response.statusCode}');
        return false;
      }
    } catch (e) {
      print('Ошибка сети updateLesson: $e');
      return false;
    }
  }

  // начать редактирование
  static Future<void> startEditing(String lessonId) async {
    try {
      await http.post(Uri.parse('$baseUrl/api/schedule/$lessonId/editing'));
    } catch (e) {
      print('Ошибка startEditing: $e');
    }
  }

  // продлить редактирование
  static Future<void> renewEditing(String lessonId) async {
    try {
      await http.put(Uri.parse('$baseUrl/api/schedule/$lessonId/editing'));
    } catch (e) {
      print('Ошибка renewEditing: $e');
    }
  }

  // закончить редактирование
  static Future<void> stopEditing(String lessonId) async {
    try {
      await http.delete(Uri.parse('$baseUrl/api/schedule/$lessonId/editing'));
    } catch (e) {
      print('Ошибка stopEditing: $e');
    }
  }
}
