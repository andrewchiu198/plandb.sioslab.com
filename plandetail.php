<?php include "templates/header.php"; ?>

<?php 
if (empty($_GET["name"])){
    echo "No planet name provided.";
    include "templates/footer.php"; 
    exit;
} else{
    $name = $_GET["name"];
}

$sql = "SELECT pl_orbper,pl_discmethod,pl_orbsmax,smax_from_orbper,pl_orbeccen,pl_orbincl,pl_bmassj,pl_bmassprov,pl_radj,rad_from_mass,pl_orbtper,pl_orblper,pl_eqt,pl_insol,pl_angsep,pl_minangsep,pl_maxangsep,ra_str,dec_str,st_dist,st_plx,gaia_plx,gaia_dist,st_optmag,st_optband,gaia_gmag,st_teff,st_mass,st_pmra,st_pmdec,gaia_pmra,gaia_pmdec,st_radv,st_spstr,st_lum,st_metfe,st_age,st_bmvj FROM KnownPlanets WHERE pl_name='".$name."'";

include("config.php"); 
$conn = new mysqli($servername, $username, $password, $dbname);
// Check connection
if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
} 
$result = $conn->query($sqlsel.$sql);
if (!$result){
    include "templates/headerclose.php"; 
    echo "Query Error:\n".$conn->error;
    $conn->close();
    include "templates/footer.php"; 
    exit;
}
if ($result->num_rows == 0) {
    include "templates/headerclose.php"; 
    echo "Planet Not Found.";
    $result->close();
    $conn->close();
    include "templates/footer.php"; 
    exit;
}
if ($result->num_rows > 1) {
    include "templates/headerclose.php"; 
    echo "Multiple matches found.";
    $result->close();
    $conn->close();
    include "templates/footer.php"; 
    exit;
}

$sql2 = "select * from PlanetOrbits where Name = '".$name."'";
$resultp = $conn->query($sql2);

?>

<script type="text/javascript" src="https://www.gstatic.com/charts/loader.js"></script>
<script type="text/javascript">

google.charts.load('current', {'packages':['line']});
google.charts.setOnLoadCallback(drawChart1);
google.charts.setOnLoadCallback(drawChart2);


function drawChart1() {
var data = new google.visualization.DataTable();
data.addColumn('number', 'Mean Anomaly (rad)');
data.addColumn('number', 'Orbital Radius (AU)');
//data.addColumn('number', 'Projected Separation (AU)');
data.addColumn('number', 'Angular Separation (mas)');

<?php 
if ($resultp && ($resultp->num_rows > 0)){
    echo "data.addRows([\n";
    $row = $resultp->fetch_assoc();
    //echo "[".$row[M].", ".$row[r].", ".$row[s].", ".$row[WA]."]";
    echo "[".$row[M].", ".$row[r].", ".$row[WA]."]";
    while($row = $resultp->fetch_assoc()) {
    //echo ",\n[".$row[M].", ".$row[r].", ".$row[s].", ".$row[WA]."]";
        echo ",\n[".$row[M].", ".$row[r].", ".$row[WA]."]";
    }
    echo "]);\n\n";
}
?>

  var options = {
    'width':500,
    'height':400,
    series: {
        0: {targetAxisIndex: 0, color: 'blue'},
        //1: {targetAxisIndex: 0},
        //2: {targetAxisIndex: 1}
        1: {targetAxisIndex: 1, color: 'red'}
    },
    legend: {position: 'none'},
    vAxes: {
        0: {title: 'Orbital Radius (AU)',textStyle: {color: 'blue'}},  
        1: {title: ' Angular Separation (mas)',textStyle: {color: 'red'}}
    },
  };

  var chart = new google.charts.Line(document.getElementById('chart_div'));
  chart.draw(data, google.charts.Line.convertOptions(options));
}

function drawChart2() {
var data = new google.visualization.DataTable();
data.addColumn('number', 'Mean Anomaly (rad)');
data.addColumn('number', '\u0394 mag');
data.addColumn('number', '\u03A6 (\u03B2) ');


<?php 
if ($resultp && ($resultp->num_rows > 0)){
    echo "data.addRows([\n";
    $resultp->data_seek(0);
    $row = $resultp->fetch_assoc();
    echo "[".$row[M].", ".$row[dMag].", ".$row[phi]."]";
    while($row = $resultp->fetch_assoc()) {
    echo ",\n[".$row[M].", ".$row[dMag].", ".$row[phi]."]";
    }
    echo "]);\n\n";
}
?>

  var options = {
    'width':500,
    'height':400,
    series: {
        0: {targetAxisIndex: 0, color: 'green'},
        1: {targetAxisIndex: 1, color: 'purple'},
    },
    legend: {position: 'none'},

    vAxes: {
        0: {title: '\u0394 mag',textStyle: {color: 'green'}},  
        1: {title: '\u03A6 (\u03B2) ',textStyle: {color: 'purple'}}
    } 
  };

  var chart = new google.charts.Line(document.getElementById('chart_div2'));
  chart.draw(data, google.charts.Line.convertOptions(options));
}

</script>


<?php include "templates/headerclose.php"; ?>

<h2> Planet Detail for 
<?php echo $name; ?>
</h2>

<div class="container">
<?php
$row = $result->fetch_assoc();
$wd = '50';
echo " <div style='float: left; width: 90%; margin-bottom: 2em;'>\n";
echo "<TABLE class='results'>\n";
echo "<TR><TH colspan='2'> Planet Properties</TH></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Discovered via</TH><TD>".$row[pl_discmethod]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Period (days)</TH><TD>".$row[pl_orbper]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Semi-major Axis (AU)</TH><TD>".$row[pl_orbsmax];
if ($row[smax_from_orbper])
    echo " (calculated from period)\n";
echo"</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Eccentricity</TH><TD>".$row[pl_orbeccen]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Inclination (deg)</TH><TD>".$row[pl_orbincl]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>".$row[pl_bmassprov]." (Jupiter Masses)</TH><TD>".$row[pl_bmassj]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Radius (Jupiter Radii)</TH><TD>".$row[pl_radj];
if ($row[rad_from_mass])
    echo " (estimated from mass)\n";
echo"</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Periapsis Passage Time (JD)</TH><TD>".$row[pl_orbtper]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Longitude of Periapsis (deg)</TH><TD>".$row[pl_orblper]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Equilibrium Temperature (K)</TH><TD>".$row[pl_eqt]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Insolation Flux (Earth fluxes)</TH><TD>".$row[pl_insor]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Angular Separation (mas)</TH><TD>".$row[pl_angsep]."</TD></TR>\n";
//echo "<TR><TH style='width:".$wd."%'>Minimum Angular Separation (mas)</TH><TD>".$row[pl_minangsep]."</TD></TR>\n";
//echo "<TR><TH style='width:".$wd."%'>Maximum Angular Separation (mas)</TH><TD>".$row[pl_maxangsep]."</TD></TR>\n";
echo "</TABLE>\n";


echo "<TABLE class='results'>\n";
echo "<TR><TH colspan='2'> Star Properties</TH></TR>\n";
echo "<TR><TH style='width:".$wd."%'>RA, DEC</TH><TD>".$row[ra_str].", ".$row[dec_str]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Distance (GAIA Distance) (pc)</TH><TD>".$row[st_dist]." (".$row[gaia_dist].")</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Parallax (GAIA Parallax) (mas)</TH><TD>".$row[st_plx]." (".$row[gaia_plx].")</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Proper Motion RA/DEC (GAIA PM) (mas/yr)</TH><TD>".$row[st_pmra].", ".$row[st_pmdec]." (".$row[gaia_pmra].", ".$row[gaia_pmdec].")</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Radial Velocity (km/s)</TH><TD>".$row[st_radv]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>".$row[st_optband]. " band Magnitude</TH><TD>".$row[st_optmag]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>GAIA G band Magnitude</TH><TD>".$row[gaia_gmag]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Effective Temperature (K)</TH><TD>".$row[st_teff]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Mass (Solar Masses)</TH><TD>".$row[st_mass]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Spectral Type</TH><TD>".$row[st_spstr]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Luminosity  (Solar Luminosities)</TH><TD>".$row[st_lum]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Metallicity (dex)</TH><TD>".$row[st_metfe]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>Age (Gyr)</TH><TD>".$row[st_age]."</TD></TR>\n";
echo "<TR><TH style='width:".$wd."%'>B-V (Johnson) (mag)</TH><TD>".$row[st_bmvj]."</TD></TR>\n";

echo "</TABLE>\n";
    
echo "</DIV><br><br>\n";

if ($resultp){
    if ($resultp->num_rows == 0){
        echo "No PlanetOrbit rows returned.";
    } else{
        echo '<div style="float: left; margin-right: 2em" id="chart_div"></div>';
        echo '<div style="float: left;" id="chart_div2"></div>';
    }
    $resultp->close();
} else{
echo "Query Error:\n".$conn->error;
}
$conn->close();
?>

</DIV>
<?php include "templates/footer.php"; ?>

