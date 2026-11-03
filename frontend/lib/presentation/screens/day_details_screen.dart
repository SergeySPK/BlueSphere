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

// Экран расписания дня
class DayDetailsScreen extends StatefulWidget {
  final int day;
  final String monthName;
  final String monthNumber;
  final String className;
  final String classId;
  final int dayLevel;
  final bool isTeacher;
  final int bannerLevel;
  final String statusDate;

  const DayDetailsScreen({
    super.key,
    required this.day,
    required this.monthName,
    required this.monthNumber,
    required this.className,
    required this.classId,
    required this.dayLevel,
    required this.bannerLevel,
    required this.statusDate,
    required this.isTeacher,
  });

  @override
  State<DayDetailsScreen> createState() => _DayDetailsScreenState();
}

class _DayDetailsScreenState extends State<DayDetailsScreen> {
  List<Lesson>? _lessons;
  bool _isLoading = true;
  int? _editingLessonNumber;

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

  Future<void> _editLesson(Lesson lesson) async {
    // 1. Начинаем сессию редактирования (POST /editing)
    try {
      await ApiService.startEditing(lesson.id);
    } catch (e) {
      // 409 = урок занят другим, 403 = нет прав и т.п.
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Не удалось начать редактирование. Возможно, урок уже редактирует другой пользователь.')));
      }
      return; // диалог не открываем
    }

    final random = Random();
    setState(() {
      _editingLessonNumber = lesson.lessonNumber;
      _randomEditColor = editColors[random.nextInt(editColors.length)];
    });

    final TextEditingController controller = TextEditingController(text: lesson.lessonType);
    if (!mounted) return;

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        return Dialog(
          backgroundColor: Colors.transparent,
          child: Container(
            padding: ps(h: 24.fw, v: 24.fh),
            decoration: BoxDecoration(color: white, borderRadius: BorderRadius.circular(16.r)),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Изменить тип урока',
                  style: TextStyle(fontFamily: 'Inter', fontSize: 18.fh, fontWeight: .w600, color: loadMax),
                ),
                SizedBox(height: 16.fh),
                TextField(
                  controller: controller,
                  autofocus: true,
                  style: TextStyle(fontFamily: 'SF Pro', fontSize: 14.fh, color: black),
                  decoration: InputDecoration(
                    hintText: 'Например: Контрольная работа',
                    hintStyle: TextStyle(color: text),
                    contentPadding: ps(h: 16.fw, v: 12.fh),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8.r),
                      borderSide: BorderSide(color: text.withOpacity(0.3)),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8.r),
                      borderSide: BorderSide(color: loadMax, width: 2.fw),
                    ),
                  ),
                ),
                SizedBox(height: 24.fh),
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    TextButton(
                      onPressed: () async {
                        try {
                          await ApiService.stopEditing(lesson.id);
                        } catch (e) {
                          debugPrint('stopEditing error: $e');
                        }
                        if (!dialogContext.mounted) return;
                        setState(() => _editingLessonNumber = null);
                        Navigator.pop(dialogContext);
                      },
                      child: Text(
                        'Отмена',
                        style: TextStyle(fontFamily: 'Inter', fontSize: 14.fh, fontWeight: .w500, color: black),
                      ),
                    ),
                    SizedBox(width: 8.fw),
                    ElevatedButton(
                      onPressed: () async {
                        final newType = controller.text.trim();

                        if (newType.isEmpty || newType == lesson.lessonType) {
                          try {
                            await ApiService.stopEditing(lesson.id);
                          } catch (e) {
                            debugPrint('stopEditing error: $e');
                          }
                          if (!dialogContext.mounted) return;
                          setState(() => _editingLessonNumber = null);
                          Navigator.pop(dialogContext);
                          return;
                        }
                        bool success = false;
                        try {
                          success = await ApiService.updateLesson(lesson.id, newType);
                        } catch (e) {
                          debugPrint('updateLesson error: $e');
                          success = false;
                        } finally {
                          // Освобождаем сессию всегда
                          try {
                            await ApiService.stopEditing(lesson.id);
                          } catch (e) {
                            debugPrint('stopEditing error: $e');
                          }
                        }

                        if (!dialogContext.mounted) return;

                        if (success) {
                          setState(() => _editingLessonNumber = null);
                          Navigator.pop(dialogContext);
                          _loadSchedule();
                        } else {
                          if (mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Не удалось сохранить изменение. Попробуйте ещё раз.')));
                          }
                          setState(() => _editingLessonNumber = null);
                          Navigator.pop(dialogContext);
                          _loadSchedule();
                        }
                      },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: loadMax,
                        padding: ps(h: 20.fw, v: 10.fh),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8.r)),
                      ),
                      child: Text(
                        'Сохранить',
                        style: TextStyle(fontFamily: 'Inter', fontSize: 14.fh, fontWeight: .w500, color: white),
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

    return Scaffold(
      backgroundColor: background,
      body: SafeArea(
        child: Column(
          children: [
            CustomHeader(title: widget.className, showBack: true, onBack: () => Navigator.pop(context)),
            Expanded(
              child: _isLoading
                  ? Center(child: CircularProgressIndicator())
                  : SingleChildScrollView(
                      padding: po(t: 8.fh, l: 16.fw, r: 16.fw),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          StatusBanner(level: widget.bannerLevel, date: widget.statusDate, showButton: false),
                          SizedBox(height: 11.fh),
                          if (_lessons != null)
                            ScheduleCard(
                              day: widget.day.toString(),
                              month: widget.monthName,
                              weekday: weekdayName,
                              lessons: _lessons!.map((l) => LessonData(number: l.lessonNumber, subject: l.subjectName, type: l.lessonType, teacherName: l.teacherName)).toList(),
                              statusColor: dayColor,
                              editingLessonNumber: _editingLessonNumber,
                              editingColor: _randomEditColor ?? loadMax,
                              onEditLesson: widget.isTeacher
                                  ? (lessonData) {
                                      final lesson = _lessons!.firstWhere((l) => l.lessonNumber == lessonData.number);
                                      _editLesson(lesson);
                                    }
                                  : null,
                            ),
                          SizedBox(height: 16.fh),
                          if (widget.isTeacher) AiRecommendationsCard(recommendations: []),
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
