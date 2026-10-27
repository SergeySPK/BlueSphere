import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import '../../domain/lesson.dart';
import '../../data/api_service.dart';
import '../uikit/colors.dart';
import '../uikit/custom_header.dart';
import '../uikit/status_banner.dart';
import '../uikit/schedule_card.dart';
import '../uikit/recommendations_block.dart';

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
        if (data != null && data.isNotEmpty) {
          _lessons = data.map((json) => Lesson.fromJson(json)).toList();
        } else {
          _lessons = [];
        }
        _isLoading = false;
      });
    }
  }

  void _editLesson(Lesson lesson) {
    setState(() {
      _editingLessonNumber = lesson.lessonNumber;
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
                        final success = await ApiService.updateLesson(lesson.id, newType, 'demo-teacher-1');
                        if (!dialogContext.mounted) return;
                        setState(() => _editingLessonNumber = null);
                        Navigator.pop(dialogContext);
                        if (success) {
                          _loadSchedule();
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

    final List<AiRecommendationItem> mockRecommendations = [AiRecommendationItem(title: '1. Разгрузить вторник:', description: 'Не назначать контрольные и дедлайны на самый напряженный день недели (9, 10, 16, 23 числа).')];

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
                      padding: po(t: 8, l: 16, r: 16, b: 80),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          StatusBanner(level: widget.bannerLevel, date: widget.statusDate, showButton: false),
                          SizedBox(height: 16.fh),
                          if (_lessons != null)
                            ScheduleCard(
                              day: widget.day.toString(),
                              month: widget.monthName,
                              weekday: 'Вторник',
                              lessons: _lessons!.map((l) => LessonData(number: l.lessonNumber, subject: l.subjectName, type: l.lessonType)).toList(),
                              statusColor: dayColor,
                              editingLessonNumber: _editingLessonNumber,
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
