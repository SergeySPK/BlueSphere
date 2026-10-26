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
        if (data != null) {
          _lessons = data.map((json) => Lesson.fromJson(json)).toList();
        }
        _isLoading = false;
      });
    }
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
    // моковые данные
    final List<AiRecommendationItem> mockRecommendations = [AiRecommendationItem(title: '1. Разгрузить вторник:', description: 'Не назначать контрольные и дедлайны на самый напряженный день недели (9, 10, 16, 23 числа).')];

    return Scaffold(
      backgroundColor: background,
      body: SafeArea(
        child: Column(
          children: [
            CustomHeader(title: widget.className, onClose: () => Navigator.pop(context), onMenu: () {}),
            Expanded(
              child: _isLoading
                  ? const Center(child: CircularProgressIndicator())
                  : SingleChildScrollView(
                      padding: po(t: 8, l: 16, r: 16, b: 80),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          StatusBanner(level: widget.bannerLevel, date: widget.statusDate),
                          SizedBox(height: 16.fh),

                          if (_lessons != null)
                            ScheduleCard(
                              day: widget.day.toString(),
                              month: widget.monthName,
                              lessons: _lessons!.map((l) => LessonData(number: l.lessonNumber, subject: l.subjectName, type: l.lessonType)).toList(),
                              statusColor: dayColor,
                              onEditLesson: (lesson) {},
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
