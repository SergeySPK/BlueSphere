import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import '../../domain/lesson.dart';
import '../../data/api_service.dart';
import '../uikit/colors.dart';
import '../uikit/custom_header.dart';
import '../uikit/status_banner.dart';
import '../uikit/schedule_card.dart';
import '../uikit/recommendations_block.dart';
import 'dart:math';

class DayDetailsScreen extends StatefulWidget {
  final int day;
  final String monthName;
  final String monthNumber;
  final String className;
  final String classId;
  final int dayLevel;
  final int bannerLevel;
  final String statusDate;

  const DayDetailsScreen({super.key, required this.day, required this.monthName, required this.monthNumber, required this.className, required this.classId, required this.dayLevel, required this.bannerLevel, required this.statusDate});

  @override
  State<DayDetailsScreen> createState() => _DayDetailsScreenState();
}

class _DayDetailsScreenState extends State<DayDetailsScreen> {
  List<Lesson>? _lessons;
  bool _isLoading = true;
  int? _editingLessonNumber;
  final editingColor = getTeacherColor('demo-teacher-1');

  @override
  void initState() {
    super.initState();
    _loadSchedule();
  }

  Future<void> _loadSchedule() async {
    final year = DateTime.now().year;
    final month = widget.monthNumber.padLeft(2, '0');
    final day = widget.day.toString().padLeft(2, '0');
    final dateStr = '$year-$month-$day';

    final data = await ApiService.getSchedule(widget.classId, dateStr);

    if (mounted) {
      setState(() {
        if (data.isNotEmpty) {
          _lessons = data.map((json) => Lesson.fromJson(json)).toList();
        } else {
          _lessons = [];
        }
        _isLoading = false;
      });
    }
  }

  Color? _randomEditColor;

  void _editLesson(Lesson lesson) {
    final random = Random();

    setState(() {
      _editingLessonNumber = lesson.lessonNumber;
      _randomEditColor = editColors[random.nextInt(editColors.length)];
    });

    final TextEditingController controller = TextEditingController(text: lesson.lessonType);

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        return Dialog(
          backgroundColor: Colors.transparent,
          child: Container(
            padding: pa(24),
            decoration: BoxDecoration(color: white, borderRadius: BorderRadius.circular(16)),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Изменить тип урока',
                  style: TextStyle(fontFamily: 'Inter', fontSize: 18, fontWeight: .w600, color: loadMax),
                ),
                SizedBox(height: 16.fh),
                TextField(
                  controller: controller,
                  autofocus: true,
                  style: TextStyle(fontFamily: 'SF Pro', fontSize: 14, color: black),
                  decoration: InputDecoration(
                    hintText: 'Например: Контрольная работа',
                    hintStyle: TextStyle(color: text),
                    contentPadding: ps(h: 16, v: 12),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8),
                      borderSide: BorderSide(color: text.withOpacity(0.3)),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8),
                      borderSide: BorderSide(color: loadMax, width: 2),
                    ),
                  ),
                ),
                SizedBox(height: 24.fh),
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    TextButton(
                      onPressed: () {
                        ApiService.stopEditing(lesson.id);
                        setState(() => _editingLessonNumber = null);
                        Navigator.pop(dialogContext);
                      },
                      child: Text(
                        'Отмена',
                        style: TextStyle(fontFamily: 'Inter', fontSize: 14, fontWeight: .w500, color: black),
                      ),
                    ),
                    SizedBox(width: 8.fw),
                    ElevatedButton(
                      onPressed: () async {
                        final newType = controller.text.trim();

                        if (newType.isEmpty || newType == lesson.lessonType) {
                          setState(() => _editingLessonNumber = null);
                          Navigator.pop(dialogContext);
                          return;
                        }
                        // отправляем на сервер
                        final success = await ApiService.updateLesson(lesson.id, newType, 'demo-teacher-1');
                        if (!dialogContext.mounted) return;
                        // сообщаем серверу, что закончили
                        await ApiService.stopEditing(lesson.id);
                        if (success) {
                          // если сервер сохранил — перезапрашиваем данные
                          setState(() => _editingLessonNumber = null);
                          Navigator.pop(dialogContext);
                          _loadSchedule();
                        } else {
                          // если сервер не сохранил (нет токена) — обновляем локально,
                          // чтобы ты видела, что интерфейс работает
                          setState(() {
                            final index = _lessons!.indexWhere((l) => l.id == lesson.id);
                            if (index != -1) {
                              _lessons![index] = Lesson(id: lesson.id, lessonNumber: lesson.lessonNumber, subjectName: lesson.subjectName, teacherName: lesson.teacherName, room: lesson.room, lessonType: newType, subgroup: lesson.subgroup);
                            }
                            _editingLessonNumber = null;
                          });
                          Navigator.pop(dialogContext);

                          print('Данные не сохранены на сервере (нужен токен авторизации)');
                        }
                      },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: loadMax,
                        padding: ps(h: 20, v: 10),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      ),

                      child: Text(
                        'Сохранить',
                        style: TextStyle(fontFamily: 'Inter', fontSize: 14, fontWeight: .w500, color: white),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Color _getLoadColor(int level) {
    switch (level) {
      case 0:
        return loadMax;
      case 1:
        return loadHigh;
      case 2:
        return loadMedium;
      case 3:
        return loadLow;
      default:
        return loadMin;
    }
  }

  @override
  Widget build(BuildContext context) {
    final Color dayColor = _getLoadColor(widget.dayLevel);
    final int year = DateTime.now().year;
    final int month = int.tryParse(widget.monthNumber) ?? DateTime.now().month;
    final DateTime date = DateTime(year, month, widget.day);
    final List<String> weekdays = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье'];
    final String weekdayName = weekdays[date.weekday - 1];

    final List<AiRecommendationItem> mockRecommendations = [AiRecommendationItem(title: '', description: '')];

    return Scaffold(
      backgroundColor: background,
      body: SafeArea(
        child: Column(
          children: [
            CustomHeader(title: widget.className, onClose: () => Navigator.pop(context), onMenu: () {}),
            Expanded(
              child: _isLoading
                  ? Center(child: CircularProgressIndicator())
                  : SingleChildScrollView(
                      padding: po(t: 8, l: 16, r: 16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          StatusBanner(level: widget.bannerLevel, date: widget.statusDate, showButton: false),
                          SizedBox(height: 16.fh),
                          if (_lessons != null)
                            ScheduleCard(
                              day: widget.day.toString(),
                              month: widget.monthName,
                              weekday: weekdayName,
                              lessons: _lessons!.map((l) => LessonData(number: l.lessonNumber, subject: l.subjectName, type: l.lessonType, teacherName: l.teacherName)).toList(),
                              statusColor: dayColor,
                              editingLessonNumber: _editingLessonNumber,
                              editingColor: _randomEditColor ?? loadMax,
                              onEditLesson: (lessonData) {
                                final lesson = _lessons!.firstWhere((l) => l.lessonNumber == lessonData.number);
                                _editLesson(lesson);
                              },
                            ),
                          SizedBox(height: 16.fh),
                          AiRecommendationsCard(recommendations: mockRecommendations),
                        ],
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}
