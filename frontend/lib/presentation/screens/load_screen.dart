import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import '../../data/api_service.dart';
import '../../domain/load_day.dart';
import '../../domain/class_status.dart';
import '../../domain/recommendation.dart';
import '../uikit/calendar.dart';
import '../uikit/colors.dart';
import '../uikit/custom_header.dart';
import '../uikit/recommendations_block.dart';
import '../uikit/status_banner.dart';
import 'day_details_screen.dart';

class LoadScreen extends StatefulWidget {
  final String classId;
  final String className;
  final VoidCallback onGoToClasses;
  final VoidCallback onGoToSummary;

  const LoadScreen({super.key, required this.classId, required this.className, required this.onGoToClasses, required this.onGoToSummary});

  @override
  State<LoadScreen> createState() => _LoadScreenState();
}

class _LoadScreenState extends State<LoadScreen> {
  List<LoadDay>? _loadDays;
  ClassStatus? _status;
  Recommendation? _recommendation;
  bool _isLoading = true;

  bool get isClassSelected => widget.classId.isNotEmpty && widget.classId != 'Выберите класс';

  @override
  void initState() {
    super.initState();
    if (isClassSelected) {
      _loadData();
    } else {
      _isLoading = false;
    }
  }

  @override
  void didUpdateWidget(covariant LoadScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.classId != widget.classId) {
      if (isClassSelected) {
        setState(() => _isLoading = true);
        _loadData();
      } else {
        setState(() => _isLoading = false);
      }
    }
  }

  Future<void> _loadData() async {
    final now = DateTime.now();
    final month = now.month.toString().padLeft(2, '0');
    final date = "${now.day.toString().padLeft(2, '0')}.${now.month.toString().padLeft(2, '0')}";

    final results = await Future.wait([ApiService.getHeatmap(widget.classId, month), ApiService.getSummary(widget.classId, date), ApiService.getRecommendations(widget.classId)]);

    if (mounted) {
      setState(() {
        _loadDays = results[0] as List<LoadDay>?;
        _status = results[1] as ClassStatus?;
        _recommendation = results[2] as Recommendation?;
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: background,
      body: SafeArea(
        child: Column(
          children: [
            CustomHeader(title: isClassSelected ? widget.className : 'Выберите класс', onClose: () {}, onMenu: () {}),
            Expanded(
              child: !isClassSelected
                  ? _buildNoClassSelected()
                  : _isLoading
                  ? Center(child: CircularProgressIndicator())
                  : SingleChildScrollView(
                      padding: po(t: 8, l: 16, r: 16, b: 80),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (_status == null)
                            Center(
                              child: Text('Не удалось загрузить статус', style: TextStyle(color: black)),
                            )
                          else
                            StatusBanner(level: _status!.level ?? 4, date: _status!.date ?? '', showButton: true, onGoToSummary: widget.onGoToSummary),
                          SizedBox(height: 16.fh),
                          if (_loadDays != null)
                            LoadCalendar(
                              date: DateTime.now(),
                              loadDays: _loadDays!,
                              onDayTap: (day) {
                                final now = DateTime.now();
                                final months = ['Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня', 'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря'];
                                final currentMonth = months[now.month - 1];
                                final currentMonthNumber = now.month.toString();
                                final dayData = _loadDays!.firstWhere((d) => d.day == day, orElse: () => LoadDay(day: day, level: 4));
                                Navigator.push(
                                  context,
                                  MaterialPageRoute(
                                    builder: (context) => DayDetailsScreen(
                                      day: day,
                                      monthName: currentMonth,
                                      monthNumber: currentMonthNumber,
                                      className: widget.className,
                                      classId: widget.classId,
                                      dayLevel: dayData.level,
                                      bannerLevel: _status?.level ?? 4,
                                      statusDate: _status?.date ?? '',
                                    ),
                                  ),
                                );
                              },
                            ),
                          SizedBox(height: 16.fh),
                          if (_recommendation != null) RecommendationsBlock(daysToReduce: _recommendation!.daysToReduce, daysToMoveTo: _recommendation!.daysToMoveTo),
                        ],
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNoClassSelected() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            'Класс не выбран',
            style: TextStyle(fontFamily: 'Inter', fontSize: 18, fontWeight: FontWeight.w600, color: black),
          ),
          SizedBox(height: 8.fh),
          Text(
            'Чтобы посмотреть нагрузку,\nвыберите класс',
            textAlign: TextAlign.center,
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 14, fontWeight: FontWeight.w400, color: text),
          ),
          SizedBox(height: 24.fh),
          ElevatedButton(
            onPressed: widget.onGoToClasses,
            style: ElevatedButton.styleFrom(
              backgroundColor: bottomBarText,
              padding: po(l: 24, r: 24, t: 12, b: 12),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
            child: Text(
              'Перейти к классам',
              style: TextStyle(fontFamily: 'Inter', fontSize: 14, fontWeight: FontWeight.w500, color: white),
            ),
          ),
        ],
      ),
    );
  }
}
