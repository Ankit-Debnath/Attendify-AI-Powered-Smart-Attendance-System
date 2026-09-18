with open('app.py', 'r') as f:
    lines = f.readlines()
# Find where student_export_pdf starts
start_idx = 0
for i, line in enumerate(lines):
    if 'def student_export_pdf():' in line:
        start_idx = i - 2
        break

# Find the end by searching for the start of error handlers
end_idx = 0
for i in range(start_idx, len(lines)):
    if 'import logging' in lines[i]:
        end_idx = i
        break

correct_student_export_pdf = """@app.route('/student/reports/export/pdf', methods=['GET'])
@login_required
def student_export_pdf():
    if session.get('role') != 'student':
        return "Unauthorized", 403
        
    class_id = request.args.get('class_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if class_id:
        conn = get_db_connection(app.config['DATABASE'])
        e = conn.execute('SELECT * FROM enrollments WHERE student_id = ? AND class_id = ?', (session['user_id'], class_id)).fetchone()
        conn.close()
        if not e:
            return "Invalid class", 400
            
    report = get_student_report(app.config['DATABASE'], session['user_id'], class_id, start_date, end_date)
    
    title = "My Attendance Report"
    
    pct = f"{report['summary']['overall_percentage']:.2f}%" if report['summary']['overall_percentage'] is not None else "N/A"
    summary = [
        f"Total Sessions: {report['summary']['sessions']}",
        f"Present: {report['summary']['present']}",
        f"Overall Attendance: {pct}"
    ]
    if start_date and end_date:
        summary.append(f"Date Range: {start_date} to {end_date}")
        
    headers = ['Date', 'Class', 'Session', 'Status']
    rows = []
    for h in report['history']:
        rows.append([h['date'], h['class_name'], h['session'], h['status']])
        
    pdf_data = generate_pdf(title, summary, headers, rows)
    
    filename = "my_attendance_report.pdf"
    return Response(pdf_data, mimetype="application/pdf", headers={"Content-Disposition": f"attachment;filename={filename}"})

"""

new_lines = lines[:start_idx] + [correct_student_export_pdf] + lines[end_idx:]

with open('app.py', 'w') as f:
    for line in new_lines:
        f.write(line)
