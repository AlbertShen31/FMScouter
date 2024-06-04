import os

# Calculate the score for each position
def calculate_score(data, key_attrs, green_attrs, blue_attrs, key_weight, green_weight, blue_weight, divisor):
    key_score = sum(data[attr] for attr in key_attrs)
    green_score = sum(data[attr] for attr in green_attrs)
    blue_score = sum(data[attr] for attr in blue_attrs)
    
    total_score = (key_score * key_weight + green_score * green_weight + blue_score * blue_weight) / divisor
    return round(total_score, 1)

def format_position_name(position):
    # Remove the underscores and use the initial of each word
    single_letter_pos = ["goalkeeper_defend", "winger_support", "winger_attack", "anchor_defend", "poacher_attack"]
    if position.lower() == "raumdeter_attack":
        return "RMD(A)"
    elif "segundo_volante" in position.lower():
        return "VOL(" + position.upper().split('_')[2][0] + ")"
    elif position.lower() == "box_to_box_midfielder_support":
        return "BBM(S)"
    elif position.lower() == "false_nine_support":
        return "F9(S)"
    elif len(position.split('_')) == 2 and (position.lower() not in single_letter_pos):
        initials = position.split('_')
        return ("".join(initials[0][:3]) + "(" + initials[1][0] + ")").upper()

    initials = [word[0] for word in position.split('_')]
    return ("".join(initials[:-1]) + "(" + initials[-1] + ")").upper()


def generate_html_multiple(dataframes, table_names, folder_name):
    def create_option_list(table_names):
        return "\n".join(f'        <option value="table{i}">{name}</option>' for i, name in enumerate(table_names))

    def create_table_divs(dataframes):
        divs = ""
        for i, df in enumerate(dataframes):
            display_style = "block" if i == 0 else "none"
            df_html = df.to_html(classes='display', border=0, index=False, table_id=f'table_{i}')
            divs += f'    <div id="table{i}" style="display:{display_style};">\n        {df_html}\n    </div>\n'
        return divs

    def create_datatable_script(dataframes):
        script = "    $(document).ready(function() {\n"
        for i in range(len(dataframes)):
            script += f'        $("#table_{i}").DataTable({{paging: false, order: [[13, "desc"]]}});\n'
        script += "    });\n"
        return script

    def create_hide_tables_script(dataframes):
        script = ""
        for i in range(len(dataframes)):
            script += f'            document.getElementById("table{i}").style.display = "none";\n'
        return script

    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Table Display</title>
            <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.11.5/css/jquery.dataTables.min.css">
            <script type="text/javascript" src="https://code.jquery.com/jquery-3.5.1.js"></script>
            <script type="text/javascript" src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.min.js"></script>
            <style>
                table, th, td {{
                    border: 1px solid black;
                    border-collapse: collapse;
                }}
                th, td {{
                    padding: 5px;
                    text-align: left;
                }}
            </style>
        </head>
        <body>

            <h2>Select a Table to Display</h2>

            <select id="tableSelect" onchange="showTable()">
        {create_option_list(table_names)}
            </select>

        {create_table_divs(dataframes)}

            <script>
        {create_datatable_script(dataframes)}

                function showTable() {{
                    var selectedTable = document.getElementById("tableSelect").value;
                    
                    // Hide all tables
        {create_hide_tables_script(dataframes)}
                    // Show the selected table
                    document.getElementById(selectedTable).style.display = "block";
                }}
            </script>

        </body>
        </html>
        """
    
    with open(f"{folder_name}/tables.html", "w") as file:
        file.write(html_content)


