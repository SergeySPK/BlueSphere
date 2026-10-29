import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import '../../data/api_service.dart';
import '../../domain/class_status.dart';
import '../uikit/colors.dart';
import '../uikit/custom_header.dart';
import '../uikit/error_screen.dart';
import '../uikit/status_banner.dart';
import '../uikit/class_summary_card.dart';
import '../uikit/survey_results_card.dart';

class SurveysScreen extends StatefulWidget {
  final String classId;
  final String className;
  final VoidCallback onGoToClasses;

  const SurveysScreen({super.key, required this.classId, required this.className, required this.onGoToClasses});

  @override
  State<SurveysScreen> createState() => _SurveysScreenState();
}

class _SurveysScreenState extends State<SurveysScreen> {
  ClassStatus? _status;
  bool _isLoading = true;
  int? _errorCode;

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
  void didUpdateWidget(covariant SurveysScreen oldWidget) {
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
    setState(() {
      _isLoading = true;
      _errorCode = null;
    });

    try {
      final now = DateTime.now();
      final date = "${now.day.toString().padLeft(2, '0')}.${now.month.toString().padLeft(2, '0')}";

      final status = await ApiService.getSummary(widget.classId, date);

      if (mounted) {
        setState(() {
          _status = status;
          _isLoading = false;
        });
      }
    } catch (e) {
      int code = 500;
      final errorString = e.toString();
      if (errorString.contains('Exception: ')) {
        code = int.tryParse(errorString.split('Exception: ')[1]) ?? 500;
      }

      if (mounted) {
        setState(() {
          _errorCode = code;
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: background,
      body: Column(
        children: [
          CustomHeader(title: isClassSelected ? widget.className : 'Выберите класс', onClose: () {}, onMenu: () {}),
          Expanded(
            child: _errorCode != null
                ? ErrorScreen(code: _errorCode!)
                : !isClassSelected
                ? _buildNoClassSelected()
                : _isLoading
                ? Center(child: CircularProgressIndicator())
                : SingleChildScrollView(
                    padding: po(t: 8, l: 16, r: 16),
                    child: Column(
                      children: [
                        if (_status != null) StatusBanner(level: _status!.level ?? 4, date: _status!.date ?? '', showButton: false),
                        SizedBox(height: 16.fh),

                        ClassSummaryCard(date: _status?.date ?? '', percentage: 70, statusText: 'НЕУДОВЛЕТВОРИТЕЛЬНО', hardestSubject: 'Математика', easiestSubject: 'Физ. культура'),
                        SizedBox(height: 16.fh),

                        SurveyResultsCard(
                          date: _status?.date ?? '09.09',
                          generalResults: [
                            SurveyResultItem(label: 'Отлично', percentage: 40),
                            SurveyResultItem(label: 'Хорошо', percentage: 10),
                            SurveyResultItem(label: 'Удовлетворительно', percentage: 5),
                            SurveyResultItem(label: 'Неудовлетворительно', percentage: 70, isHighlighted: true),
                            SurveyResultItem(label: 'Плохо', percentage: 2),
                          ],
                          stressSubjects: [
                            SurveyResultItem(label: 'Физ. культура', percentage: 0),
                            SurveyResultItem(label: 'История', percentage: 8),
                            SurveyResultItem(label: 'Русский язык', percentage: 10),
                            SurveyResultItem(label: 'Математика', percentage: 70, isHighlighted: true),
                            SurveyResultItem(label: 'Никакой', percentage: 2),
                          ],
                          easySubjects: [
                            SurveyResultItem(label: 'Физ. культура', percentage: 70, isHighlighted: true),
                            SurveyResultItem(label: 'История', percentage: 10),
                            SurveyResultItem(label: 'Русский язык', percentage: 18),
                            SurveyResultItem(label: 'Математика', percentage: 0),
                            SurveyResultItem(label: 'Никакой', percentage: 2),
                          ],
                        ),
                      ],
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  // заглушка
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
            'Чтобы посмотреть опросы,\nвыберите класс',
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
